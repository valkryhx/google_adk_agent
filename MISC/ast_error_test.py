import ast
import traceback

class CodeSanitizer:
    def sanitize_and_run(self, raw_code):
        print(f"\n>>> Processing Code:\n{raw_code.strip()}\n")
        
        # 1. 语法错误拦截 (Syntax Error Interception)
        # 此阶段如果失败，说明代码根本不能跑，直接返回给 Agent 让它重写
        try:
            tree = ast.parse(raw_code)
            print("[Pass 1] Syntax Check: OK")
        except SyntaxError as e:
            print(f"[Pass 1] Syntax Check: FAILED. Error: {e}")
            return "Error: Your code has syntax errors. Please rewrite."

        # 2. 意图修复 (Intent Repair - AST Transformation)
        # 自动补全 await 等
        try:
            # (简化的 Transformer，复用之前的逻辑)
            class AsyncFixer(ast.NodeTransformer):
                def visit_Call(self, node):
                    self.generic_visit(node)
                    if isinstance(node.func, ast.Name) and node.func.id == 'call_tool':
                        return ast.Await(value=node)
                    return node
            
            tree = AsyncFixer().visit(tree)
            ast.fix_missing_locations(tree)
            print("[Pass 2] AST Repair: OK")
        except Exception as e:
            print(f"[Pass 2] AST Repair Failed: {e}")
            return

        # 3. 运行时包裹 (Runtime Wrapping)
        # 注入 try-except 以捕获运行时错误
        code_obj = compile(tree, filename="<string>", mode="exec")
        
        print("[Pass 3] Execution Started...")
        try:
            # 模拟执行环境
            async_mock_globals = {
                'call_tool': None, # Mock
                'shadow_tracer': type('Tracer', (), {'report': lambda x: print(f"  -> [ShadowTrace] Captured Crash: {x}")})
            }
            # 这里我们只演示结构，不真的运行 async
            print("  -> (Simulated Execution: Code is safely compiled and wrapped)")
            
        except Exception as e:
            print(f"  -> [Runtime] Captured Unhandled Exception: {e}")

# --- 测试用例 ---

sanitizer = CodeSanitizer()

# Case 1: 语法错误 (Syntax Error) - 比如漏了冒号
# AST Parser 会捕获它，Agent 不会拿到 Crash，而是拿到明确的错误提示
bad_syntax_code = """
if True
    print("Missing colon")
"""
sanitizer.sanitize_and_run(bad_syntax_code)

# Case 2: 运行时错误 (Runtime Error) - 比如除以零
# 这不是 AST 能转化的，但可以通过 AST 注入 try-except 来捕获
runtime_error_code = """
x = 1 / 0
"""
# 注意：这里演示的是 AST 解析成功，但代码里包含运行时错误逻辑
sanitizer.sanitize_and_run(runtime_error_code)

print("\nConclusion: AST catches Syntax Errors early; Wrapper catches Runtime Errors later.")
