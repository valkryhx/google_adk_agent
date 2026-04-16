const assert = require('node:assert/strict');
const StreamDedup = require('../src/adk_agent/static/stream_dedup.js');

assert.equal(
  StreamDedup.trimTextChunkAfterThoughtOverlap(
    '我需要先分析问题。最终答案是 X。',
    '我需要先分析问题。',
    true,
  ),
  '最终答案是 X。',
);

assert.equal(
  StreamDedup.trimTextChunkAfterThoughtOverlap(
    '结论 B。',
    '先想 A。',
    true,
  ),
  '结论 B。',
);

assert.equal(
  StreamDedup.trimTextChunkAfterThoughtOverlap(
    '我需要先分析问题。第二句。',
    '我需要先分析问题。',
    false,
  ),
  '我需要先分析问题。第二句。',
);

assert.deepEqual(
  StreamDedup.stripLeakedThinkText(
    '执行超时了，让我尝试使用更简单的方法：\n在Windows环境下，我可以使用 PowerShell 的 Get-Date 命令：\n</think>\n让我换用 Windows PowerShell 命令来获取时间：'
  ),
  {
    content: '让我换用 Windows PowerShell 命令来获取时间：',
    hadLeak: true,
  },
);

assert.deepEqual(
  StreamDedup.stripLeakedThinkText('当前时间：2026-04-16 19:17:38 星期四'),
  {
    content: '当前时间：2026-04-16 19:17:38 星期四',
    hadLeak: false,
  },
);
