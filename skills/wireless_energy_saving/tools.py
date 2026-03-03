from playwright.async_api import async_playwright, Error as PlaywrightError
from typing import Dict, Any, List

async def fetch_engblacklist_barchart(date: str, network: str) -> Dict[str, Any]:
    """
    分析产品工单白名单柱状图数据的专属 Skill。
    该工具会自动连接用户本地已打开并登录的 Chrome 浏览器 (需开启 9222 调试端口)，
    动态提取前端 Session Token 并静默拉取数据。

    Args:
        date (str): 查询日期，格式必须为 "YYYY-MM-DD" (例如 "2026-03-03")。
        network (str): 网络类型，支持 "LTE" 或 "NR"。

    Returns:
        Dict[str, Any]: 包含 "code" 和 "data" 的标准 JSON 响应。如果出错会返回 "error" 字段。
    """
    
    # 目标系统的域名关键字，用于在众多标签页中精准定位工单系统
    TARGET_HOST = "192.168.188.1"
    TARGET_URL = "http://192.168.188.1:8080/ips/back/commonframe/engblacklist/getWhiteBarChart"

    async with async_playwright() as p:
        browser = None
        try:
            # 1. 寄生模式：连接本地 9222 端口的活动 Chrome
            # 前置条件：必须通过 chrome.exe --remote-debugging-port=9222 启动浏览器
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            
            # 2. 遍历所有打开的 Tab 页，寻找包含工单系统域名的页面
            target_page = None
            for page in context.pages:
                if TARGET_HOST in page.url:
                    target_page = page
                    break
            
            if not target_page:
                return {
                    "error": f"未找到包含 {TARGET_HOST} 的标签页，请确保浏览器已打开并停留在工单系统页面。"
                }

            # 3. 构建 JS 内鬼代码 (定义为一个接收参数的 async 函数)
            js_code = """
            async ([reqDate, reqNetwork, apiUrl]) => {
                // 就地取材：提取并解析包装在 sessionStorage 中的 Token
                const rawStorage = window.sessionStorage.getItem('powersaving-access_token');
                if (!rawStorage) {
                    throw new Error("Session中未找到 powersaving-access_token，请确认系统已登录！");
                }
                
                let liveToken;
                try {
                    liveToken = JSON.parse(rawStorage).content;
                } catch (e) {
                    throw new Error("Token 解析失败，数据格式异常！");
                }

                if (!liveToken) {
                    throw new Error("未能从 sessionStorage 中提取到有效 content Token！");
                }

                // 构造请求载荷
                const payload = { 
                    date: reqDate, 
                    netWork: reqNetwork 
                };

                // 发起请求
                const response = await fetch(apiUrl, {
                    headers: {
                        "accept": "application/json, text/plain, */*",
                        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                        "authorization": `Bearer ${liveToken}`,
                        "content-type": "application/json"
                    },
                    method: "POST",
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    throw new Error(`HTTP 异常! 状态码: ${response.status}`);
                }

                // 返回最终的 JSON 数据
                return await response.json();
            }
            """
            
            # 4. 在目标页面的上下文中执行 JS，并安全地传入 Python 参数
            result = await target_page.evaluate(js_code, [date, network, TARGET_URL])
            return result
            
        except PlaywrightError as pe:
            # 捕获 CDP 连接失败等浏览器层面异常
            if "Connection refused" in str(pe) or "No connection" in str(pe):
                return {"error": "无法连接到浏览器，请确认 Chrome 已通过 --remote-debugging-port=9222 启动。"}
            return {"error": f"浏览器自动化执行失败: {str(pe)}"}
            
        except Exception as e:
            # 捕获内部 JS 抛出的业务异常 (如未登录、Token错误等)
            return {"error": f"数据抓取异常: {str(e)}"}
            
        finally:
            # 5. 安全退出：只断开 CDP 连接，绝不能关闭用户的真实浏览器！
            if browser:
                await browser.close()

async def fetch_whitelist_cell_list(
    startTime: str,
    endTime: str,
    distName: str = None,
    neName: str = None,
    networkName: str = "",
    vendorName: str = None,
    jdType: str = None,
    page: int = 1,
    limit: int = 20
) -> Dict[str, Any]:
    """
    查询白名单小区列表的专属 Skill。
    支持多种过滤条件：地市、网元名称、网络类型、厂家、节点类型以及时间范围。

    Args:
        startTime (str): 开始时间 (YYYY-MM-DD)。
        endTime (str): 结束时间 (YYYY-MM-DD)。
        distName (str, optional): 地市名称 (如 "武汉市")。
        neName (str, optional): 网元名称/ID。
        networkName (str, optional): 网络类型，默认空字符串(查全部)，可传"LTE","NR"。
        vendorName (str, optional): 厂家名称 (如 "华为")。
        jdType (str, optional): 节点类型 (如 "符号关断")。
        page (int, optional): 页码，默认 1。
        limit (int, optional): 每页条数，默认 20。

    Returns:
        Dict[str, Any]: 包含分页数据的标准 JSON 响应。
    """
    
    TARGET_HOST = "192.168.188.1"
    TARGET_URL = "http://192.168.188.1:8080/ips/back/commonframe/engblacklist/subjectiveReason/Qry"

    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            
            target_page = None
            for page_obj in context.pages:
                if TARGET_HOST in page_obj.url:
                    target_page = page_obj
                    break
            
            if not target_page:
                return {"error": f"未找到包含 {TARGET_HOST} 的标签页，请确保浏览器已登录工单系统。"}

            # 构造 Payload
            payload = {
                "startTime": startTime,
                "endTime": endTime,
                "networkName": networkName,
                "page": page,
                "limit": limit
            }
            if distName: payload["distName"] = distName
            if neName: payload["neName"] = neName
            if vendorName: payload["vendorName"] = vendorName
            if jdType: payload["jdType"] = jdType

            js_code = """
            async ([apiUrl, payload]) => {
                const rawStorage = window.sessionStorage.getItem('powersaving-access_token');
                if (!rawStorage) throw new Error("Session中未找到 powersaving-access_token");
                
                const liveToken = JSON.parse(rawStorage).content;
                if (!liveToken) throw new Error("Token 解析失败");

                const response = await fetch(apiUrl, {
                    headers: {
                        "accept": "application/json, text/plain, */*",
                        "authorization": `Bearer ${liveToken}`,
                        "content-type": "application/json"
                    },
                    method: "POST",
                    body: JSON.stringify(payload)
                });

                if (!response.ok) throw new Error(`HTTP 异常! 状态码: ${response.status}`);
                return await response.json();
            }
            """
            
            result = await target_page.evaluate(js_code, [TARGET_URL, payload])
            return result
            
        except Exception as e:
            return {"error": f"功能执行失败: {str(e)}"}
        finally:
            if browser:
                await browser.close()

def get_tools(*args, **kwargs) -> List:
    return [fetch_engblacklist_barchart, fetch_whitelist_cell_list]
