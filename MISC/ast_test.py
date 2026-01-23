import ast

# 模拟用户写的"不完美"代码：
# 1. 忘记写 await
# 2. 没有错误处理
user_code = """
print("Starting task...")
x = call_tool('web_search', query='Apple')
y = call_tool('data_analysis', data=x)
print(f"Finished: {y}")
"""

print(f"--- [Original User Code] ---\n{user_code}\n----------------------------")

class RobustTransformer(ast.NodeTransformer):
    def visit_Call(self, node):
        self.generic_visit(node)
        # 1. 自动补全 await: 将 call_tool(...) 变为 await call_tool(...)
        if isinstance(node.func, ast.Name) and node.func.id == 'call_tool':
            return ast.Await(value=node)
        return node

def inject_global_try_except(tree):
    # 2. 自动包裹 Try-Except: 将所有代码放入 try 块中
    # 构造 except Exception as e: 块
    handler = ast.ExceptHandler(
        type=ast.Name(id='Exception', ctx=ast.Load()),
        name='e',
        body=[
            # 模拟: shadow_tracer.report_crash(e)
            ast.Expr(value=ast.Call(
                func=ast.Attribute(value=ast.Name(id='shadow_tracer', ctx=ast.Load()), attr='report_crash', ctx=ast.Load()),
                args=[ast.Name(id='e', ctx=ast.Load())],
                keywords=[]
            )),
            # reraise
            ast.Raise()
        ]
    )
    
    # 将原有的 body 放入 try
    try_node = ast.Try(
        body=tree.body,
        handlers=[handler],
        orelse=[],
        finalbody=[]
    )
    
    # 替换整个模块的 body
    tree.body = [try_node]
    return tree

# --- 执行转换 ---
tree = ast.parse(user_code)

# Step 1: 补全 await
tree = RobustTransformer().visit(tree)

# Step 2: 注入全局 Try-Except
tree = inject_global_try_except(tree)

# Step 3: 修复节点位置信息
ast.fix_missing_locations(tree)

# --- 输出结果 ---
print(f"--- [Transformed Robust Code] ---\n{ast.unparse(tree)}\n-----------------------------")
