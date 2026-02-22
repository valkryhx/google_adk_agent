
Gemini said
要想实现真正的**实时流式（Real-time Streaming）**语音输入（即：你一边说，屏幕上一边出字，像真正的 Ciri/Jarvis 那样），不能用普通的 HTTP 接口（因为 HTTP 是“请求-响应”模式，有延迟）。

我们需要使用 WebSocket 技术，并在前端使用 AudioContext 实时抓取麦克风的数据流。

这里是基于你现有项目的全套改造方案。

第一步：后端改造 (main_web_start_steering.py)
我们需要：

引入 WebSocket 支持。

加载 Online (流式) Paraformer 模型，而不是 Offline 模型。

添加一个 WebSocket 路由来处理音频流。

1. 修改导入部分 (Imports)
在文件顶部添加：

Python
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
import sherpa_onnx
2. 初始化流式 STT 模型
在全局变量区域（session_manager 附近）添加。注意这里用的是 OnlineRecognizer（流式识别器）。

Python
# ==========================================
# [新增] 实时流式 STT 引擎
# ==========================================
stt_stream_recognizer = None

def init_streaming_stt():
    """初始化流式 Paraformer 模型"""
    global stt_stream_recognizer
    try:
        print("[STT] 正在加载流式 Paraformer 模型...")
        # 请根据你实际的模型路径修改
        model_dir = "./model" 
        
        # 检查文件是否存在
        if not os.path.exists(os.path.join(model_dir, "encoder.int8.onnx")):
             print(f"[STT] ⚠️ 模型未找到，请检查 {model_dir}")
             return

        stt_stream_recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
            tokens=os.path.join(model_dir, "tokens.txt"),
            encoder=os.path.join(model_dir, "encoder.int8.onnx"),
            decoder=os.path.join(model_dir, "decoder.int8.onnx"),
            num_threads=1,
            sample_rate=16000,
            feature_dim=80,
            enable_endpoint_detection=True, # 开启自动断句检测
            rule1_min_trailing_silence=2.0,
            rule2_min_trailing_silence=1.0,
            rule3_min_utterance_length=float("inf"),
            decoding_method="greedy_search",
            provider="cpu"
        )
        print("[STT] ✅ 流式 STT 引擎就绪")
    except Exception as e:
        print(f"[STT] ❌ 引擎加载失败: {e}")

# 【重要】记得在 startup_event 里调用它
@app.on_event("startup")
async def startup_event():
    # ... 原有代码 ...
    init_streaming_stt() # <--- 加这一行
    # ... 原有代码 ...
3. 添加 WebSocket 接口
在 app = FastAPI() 之后添加：

Python
@app.websocket("/ws/audio")
async def websocket_audio_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("[WS] 前端已连接语音流")
    
    global stt_stream_recognizer
    if not stt_stream_recognizer:
        await websocket.close(code=1011, reason="STT model not initialized")
        return

    # 为每个连接创建一个独立的识别流
    stream = stt_stream_recognizer.create_stream()
    last_text = ""

    try:
        while True:
            # 1. 接收前端发来的二进制音频数据 (Float32 格式)
            data = await websocket.receive_bytes()
            
            # 2. 转换数据格式
            # 前端发来的是 bytes，我们需要转回 numpy float32 数组
            samples = np.frombuffer(data, dtype=np.float32)
            
            # 3. 喂给模型
            # 关键点：假设前端会做好重采样发 16k，或者前端发原始采样率我们在这里处理
            # 为了简单稳定，建议前端发 16000Hz 的数据
            stream.accept_waveform(16000, samples)
            
            # 4. 解码
            while stt_stream_recognizer.is_ready(stream):
                stt_stream_recognizer.decode_stream(stream)
            
            # 5. 获取结果
            text = stt_stream_recognizer.get_result(stream)
            
            # 6. 如果有新内容，发回前端
            if text != last_text:
                last_text = text
                # 发送 JSON，包含 is_final 标记
                is_endpoint = stt_stream_recognizer.is_endpoint(stream)
                await websocket.send_json({
                    "text": text,
                    "is_final": is_endpoint
                })
                
                # 如果检测到一句话结束，重置流
                if is_endpoint:
                    stt_stream_recognizer.reset(stream)
                    last_text = ""

    except WebSocketDisconnect:
        print("[WS] 语音连接断开")
    except Exception as e:
        print(f"[WS] 异常: {e}")
第二步：前端改造 (script.js)
前端需要做的工作最复杂：采集麦克风 -> 重采样到 16000Hz -> 通过 WebSocket 发送。

在 script.js 中，找到 micBtn 的相关逻辑，完全替换为以下代码：

JavaScript
// ==========================================
// [Real-time] 实时语音输入逻辑
// ==========================================
let audioContext = null;
let scriptProcessor = null;
let mediaStreamSource = null;
let websocket = null;
let isRecording = false;

const micBtn = document.getElementById('micBtn');

if (micBtn) {
    micBtn.addEventListener('click', toggleRecording);
}

async function toggleRecording() {
    if (!isRecording) {
        startRecording();
    } else {
        stopRecording();
    }
}

async function startRecording() {
    try {
        // 1. 获取麦克风流
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        
        // 2. 初始化 WebSocket
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        websocket = new WebSocket(`${protocol}//${window.location.host}/ws/audio`);
        
        websocket.onopen = () => {
            console.log('[WS] 连接已建立');
            initAudioProcessing(stream);
        };

        websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            const text = data.text;
            
            if (text) {
                // 实时更新输入框
                // 逻辑：找到输入框里最后一段正在输入的文字并替换，或者直接追加
                // 这里采用简单策略：每次都把识别到的内容显示在输入框里
                
                // 更加智能的 UI 更新逻辑：
                // 如果是 interim (中间结果)，显示灰色？
                // 这里直接简单粗暴填入
                userInput.value = text;
                // 自动调整高度
                userInput.style.height = 'auto';
                userInput.style.height = (userInput.scrollHeight) + 'px';
            }
            
            if (data.is_final) {
                // 如果后端说这句话结束了，可以考虑自动发送，或者留给用户确认
                // sendMessage(); // 如果你想说完自动发送，取消这行注释
            }
        };
        
        // UI 更新
        isRecording = true;
        micBtn.style.color = '#ea4335';
        micBtn.style.backgroundColor = '#fce8e6';
        micBtn.querySelector('span').textContent = 'mic_off'; // 变成“关麦”图标
        userInput.placeholder = '正在实时识别...';
        userInput.value = ''; // 清空输入框准备听写

    } catch (e) {
        console.error('录音启动失败:', e);
        alert('无法启动录音: ' + e.message);
    }
}

function stopRecording() {
    isRecording = false;
    
    // 关闭各种流
    if (scriptProcessor) {
        scriptProcessor.disconnect();
        scriptProcessor = null;
    }
    if (mediaStreamSource) {
        mediaStreamSource.disconnect();
        mediaStreamSource = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }
    if (websocket) {
        websocket.close();
        websocket = null;
    }

    // UI 恢复
    micBtn.style.color = '';
    micBtn.style.backgroundColor = '';
    micBtn.querySelector('span').textContent = 'mic';
    userInput.placeholder = '问问 Ciri';
}

function initAudioProcessing(stream) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    mediaStreamSource = audioContext.createMediaStreamSource(stream);
    
    // 创建脚本处理器：bufferSize 4096, 1 input channel, 1 output channel
    scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);
    
    mediaStreamSource.connect(scriptProcessor);
    scriptProcessor.connect(audioContext.destination);

    scriptProcessor.onaudioprocess = (audioProcessingEvent) => {
        if (!websocket || websocket.readyState !== WebSocket.OPEN) return;

        // 获取原始音频数据 (Float32Array)
        const inputBuffer = audioProcessingEvent.inputBuffer;
        const inputData = inputBuffer.getChannelData(0); // 单声道
        
        // **核心：降采样 (Downsampling)**
        // 浏览器通常是 44100Hz 或 48000Hz，Paraformer 需要 16000Hz
        const targetRate = 16000;
        const sampleRate = audioContext.sampleRate;
        
        if (sampleRate !== targetRate) {
            const resampled = downsampleBuffer(inputData, sampleRate, targetRate);
            websocket.send(resampled); // 发送重采样后的数据
        } else {
            websocket.send(inputData);
        }
    };
}

// 简单的线性插值重采样算法
function downsampleBuffer(buffer, sampleRate, outSampleRate) {
    if (outSampleRate == sampleRate) {
        return buffer;
    }
    if (outSampleRate > sampleRate) {
        throw "downsampling rate show be smaller than original sample rate";
    }
    var sampleRateRatio = sampleRate / outSampleRate;
    var newLength = Math.round(buffer.length / sampleRateRatio);
    var result = new Float32Array(newLength);
    var offsetResult = 0;
    var offsetBuffer = 0;
    while (offsetResult < result.length) {
        var nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
        var accum = 0, count = 0;
        for (var i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
            accum += buffer[i];
            count++;
        }
        result[offsetResult] = accum / count;
        offsetResult++;
        offsetBuffer = nextOffsetBuffer;
    }
    return result;
}
改造关键点解析
WebSocket 全双工通信：

不像之前的 POST 请求发完就断，WebSocket 建立了一条长连接。

前端每采集到 4096 个采样点（约 0.1 秒），就通过管道扔给后端。

后端实时解码，一有结果（哪怕是中间结果）就马上发回来。

前端重采样 (Downsampling)：

这是最坑的地方。浏览器麦克风通常是 48k，但 Paraformer 模型必须要 16k。

如果在后端做重采样，会浪费网络带宽（传 48k 的数据量是 16k 的 3 倍）。

我在 JS 里加了一个 downsampleBuffer 函数，在发送前把数据“压缩”到 16k，既省流量又减轻后端负担。

用户体验：

现在你点击麦克风，它会变红。

你一边说，输入框里的字会一个个蹦出来，就像真正的 Ciri 一样。

再次点击麦克风，停止识别，然后你可以手动点发送。

现在，请把这两段代码分别更新到你的 python 和 js 文件中，重启服务器，享受丝滑的实时语音输入吧！

You said
micBtn 之前的逻辑是什么

Gemini said
根据你提供的 script.js 和 index.html 源代码来看，之前的麦克风按钮没有任何逻辑，它只是一个静态的 UI 装饰品。

具体分析如下：

在 HTML 中 (index.html)：
它只是被放置在输入框旁边，甚至没有 id 属性，只有样式类：

HTML
<button class="icon-btn"><span class="material-symbols-outlined">mic</span></button>
在 JavaScript 中 (script.js)：
代码中定义了 sendBtn（发送）、stopBtn（停止）、uploadBtn（上传图片）的逻辑，但完全没有获取或操作麦克风按钮的代码。点击它不会触发任何 JS 事件，也就不会有任何反应。

总结
你现在的改造是从 “零” 开始给这个按钮赋予生命。之前它不仅不支持流式输入，连录音文件上传的功能都没有，仅仅是个占位图标。