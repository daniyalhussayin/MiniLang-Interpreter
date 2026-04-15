import sys
import re
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTextEdit, QPushButton, QTabWidget, 
                             QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter)
from PyQt6.QtGui import (QFont, QColor)
from PyQt6.QtCore import Qt

TOKEN_TYPES = [
    ('NUMBER',   r'\d+'),
    ('STRING',   r'"[^"]*"'),
    ('IF',       r'if\b'),
    ('ELSE',     r'else\b'),
    ('PRINT',    r'print\b'),
    ('ID',       r'[a-zA-Z_]\w*'),
    ('EQ',       r'=='),           
    ('ASSIGN',   r'='),            
    ('OP',       r'[+\-*/><]+'),   
    ('COMMA',    r','),
    ('LBRACE',   r'\{'),
    ('RBRACE',   r'\}'),
    ('LPAREN',   r'\('),
    ('RPAREN',   r'\)'),
    ('SKIP',     r'[ \t\n\r]+'),
    ('MISMATCH', r'.'),
]

def lex(code):
    tokens = []
    regex = '|'.join(f'(?P<{name}>{pattern})' for name, pattern in TOKEN_TYPES)
    for mo in re.finditer(regex, code):
        kind = mo.lastgroup
        value = mo.group().strip()
        if kind == 'SKIP': continue
        elif kind == 'MISMATCH': raise RuntimeError(f"Lexical Error: Unknown character '{value}'")
        tokens.append((kind, value))
    return tokens

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self, offset=0):
        if self.pos + offset < len(self.tokens): return self.tokens[self.pos + offset]
        return (None, None)

    def consume(self, expected=None):
        kind, value = self.peek()
        if expected and kind != expected:
            raise Exception(f"Syntax Error: Expected {expected} but got {kind} ('{value}')")
        self.pos += 1
        return value

    def parse(self):
        nodes = []
        while self.pos < len(self.tokens):
            nodes.append(self.parse_statement())
        return nodes

    def parse_statement(self):
        kind, _ = self.peek()
        if kind == 'IF': return self.parse_if()
        if kind == 'PRINT': return self.parse_print()
        if kind == 'ID' and self.peek(1)[0] == 'ASSIGN': return self.parse_assignment()
        raise Exception(f"Unknown statement starting with '{self.peek()[1]}'")

    def parse_assignment(self):
        name = self.consume('ID')
        self.consume('ASSIGN')
        return {'type': 'Assignment', 'target': name, 'value': self.parse_expression()}

    def parse_print(self):
        self.consume('PRINT')
        self.consume('LPAREN')
        args = [self.parse_expression()]
        while self.peek()[0] == 'COMMA':
            self.consume('COMMA')
            args.append(self.parse_expression())
        self.consume('RPAREN')
        return {'type': 'Print', 'arguments': args}

    def parse_expression(self):
        left = self.parse_term()
        while self.peek()[0] == 'OP' and self.peek()[1] in ('+', '-'):
            op = self.consume('OP')
            right = self.parse_term()
            left = {'type': 'BinaryOp', 'op': op, 'left': left, 'right': right}
        return left

    def parse_term(self):
        left = self.parse_factor()
        while self.peek()[0] == 'OP' and self.peek()[1] in ('*', '/'):
            op = self.consume('OP')
            right = self.parse_factor()
            left = {'type': 'BinaryOp', 'op': op, 'left': left, 'right': right}
        return left

    def parse_factor(self):
        kind, val = self.peek()
        if kind in ('NUMBER', 'STRING', 'ID'):
            self.consume()
            return {'type': kind, 'value': val}
        raise Exception(f"Expected Value, got {kind}")

    def parse_if(self):
        self.consume('IF')
        left = self.parse_expression()
        op_k, op_v = self.peek()
        if op_v not in ('>', '<', '=='): raise Exception("Expected comparison operator in IF")
        self.consume()
        right = self.parse_expression()
        self.consume('LBRACE')
        body = []
        while self.peek()[0] != 'RBRACE':
            body.append(self.parse_statement())
        self.consume('RBRACE')
        return {'type': 'IfStatement', 'condition': {'type': 'BinaryOp', 'left': left, 'op': op_v, 'right': right}, 'body': body}

class TACGenerator:
    def __init__(self):
        self.temp_count = 0
        self.instructions = []

    def new_temp(self):
        self.temp_count += 1
        return f"t{self.temp_count}"

    def generate(self, node):
        tag = node['type']
        if tag == 'Assignment':
            res = self.gen_expr(node['value'])
            self.instructions.append(f"{node['target']} = {res}")
        elif tag == 'Print':
            for arg in node['arguments']:
                res = self.gen_expr(arg)
                self.instructions.append(f"PARAM {res}")
            self.instructions.append(f"CALL print, {len(node['arguments'])}")
        elif tag == 'IfStatement':
            cond = node['condition']
            res_l, res_r = self.gen_expr(cond['left']), self.gen_expr(cond['right'])
            self.instructions.append(f"IF {res_l} {cond['op']} {res_r} GOTO L_START")
            self.instructions.append("GOTO L_END")
            self.instructions.append("LABEL L_START")
            for s in node['body']: self.generate(s)
            self.instructions.append("LABEL L_END")

    def gen_expr(self, expr):
        if expr['type'] in ('NUMBER', 'ID', 'STRING'): return expr['value']
        if expr['type'] == 'BinaryOp':
            l_res, r_res = self.gen_expr(expr['left']), self.gen_expr(expr['right'])
            temp = self.new_temp()
            # FIXED: Removed the invalid 'res_r' check and used 'r_res' directly
            self.instructions.append(f"{temp} = {l_res} {expr['op']} {r_res}")
            return temp

#GUI APPLICATION

class CompilerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mini-Lang Compiler")
        self.resize(1300, 850)
        self.vars = {}
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #0f172a; } /* Deep Dark Background */
            
            /* Tab Widget Styling */
            QTabWidget::pane { 
                border: 1px solid #334155; 
                border-radius: 12px; 
                background: #1e293b; /* Darker Blue for content */
            }
            QTabBar::tab { 
                background: #1e293b; 
                color: #94a3b8; 
                padding: 10px 20px; 
                border-top-left-radius: 8px; 
                border-top-right-radius: 8px; 
                margin-right: 2px;
                font-weight: bold;
            }
            QTabBar::tab:selected { 
                background: #3b82f6; 
                color: white; 
            }
            QTabBar::tab:hover {
                background: #2d3e5a;
            }

            /* Editor and Logs */
            QTextEdit { 
                background-color: #1e293b; 
                color: #e2e8f0; 
                border: 1px solid #334155; 
                border-radius: 10px; 
                padding: 10px;
                selection-background-color: #3b82f6;
            }

            /* Tables */
            QTableWidget { 
                background-color: #1e293b; 
                color: #e2e8f0; 
                gridline-color: #334155; 
                border-radius: 10px;
                border: 1px solid #334155;
            }
            QHeaderView::section {
                background-color: #334155;
                color: white;
                padding: 5px;
                border: none;
            }

            /* Buttons */
            QPushButton { 
                background-color: #2563eb; 
                color: white; 
                border-radius: 12px; 
                font-weight: bold; 
                font-size: 16px; 
                border: 1px solid #3b82f6;
            }
            QPushButton:hover { 
                background-color: #1d4ed8; 
                border: 1px solid #60a5fa;
            }
            QPushButton:pressed {
                background-color: #1e3a8a;
            }

            /* Labels */
            QLabel { 
                color: #38bdf8; /* Neon Blueish Title */
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(25)

        # EDITOR (Left Side)
        left_side = QVBoxLayout()
        title_label = QLabel("🛠️ Mini-Lang Compiler") 
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter) # Center alignment
        title_label.setStyleSheet("""
            font-size: 28px; 
            font-weight: 800; 
            color: #ffffff;  /* Yeh raha pure white color */
            margin-bottom: 15px;
            padding: 10px;
            letter-spacing: 1px; /* Thora sa gap text ke beech mein */
        """)
        left_side.addWidget(title_label)

        self.code_editor = QTextEdit()
        self.code_editor.setPlaceholderText("Write your code here...") # Aesthetic touch
        self.code_editor.setFont(QFont("Consolas", 13))
        
        self.run_btn = QPushButton("🚀 COMPILE & EXECUTE")
        self.run_btn.setFixedHeight(60)
        self.run_btn.clicked.connect(self.compile_pipeline)
        
        left_side.addWidget(self.code_editor)
        left_side.addWidget(self.run_btn)

        # TABS
        self.tabs = QTabWidget()
        
        self.lexer_table = QTableWidget()
        self.lexer_table.setColumnCount(2)
        self.lexer_table.setHorizontalHeaderLabels(["Token Type", "Lexeme"])
        self.lexer_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.ast_view = QTextEdit()
        self.ast_view.setReadOnly(True)
        self.ast_view.setFont(QFont("Consolas", 11))

        self.tac_view = QTextEdit()
        self.tac_view.setReadOnly(True)
        self.tac_view.setFont(QFont("Consolas", 14)) # Font size 14 kar diya hy
        self.tac_view.setStyleSheet("color: #fbbf24; background-color: #1e293b; padding: 15px;") # Amber color for TAC text

        # Interpreter
        interp_page = QWidget()
        interp_layout = QVBoxLayout(interp_page)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.exec_log = QTextEdit()
        self.exec_log.setReadOnly(True)
        self.exec_log.setStyleSheet("background-color: #0f172a; color: #38bdf8; border-radius: 15px;")
        self.sym_table = QTableWidget()
        self.sym_table.setColumnCount(2)
        self.sym_table.setHorizontalHeaderLabels(["Variable", "Value"])
        self.sym_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        splitter.addWidget(self.exec_log)
        splitter.addWidget(self.sym_table)
        interp_layout.addWidget(splitter)

        self.tabs.addTab(self.lexer_table, "Lexer")
        self.tabs.addTab(self.ast_view, "Parser (AST)")
        self.tabs.addTab(self.tac_view, "TAC")
        self.tabs.addTab(interp_page, "Interpreter")

        main_layout.addLayout(left_side, 2)
        main_layout.addWidget(self.tabs, 3)

    def format_ast(self, node, indent=""):
        if isinstance(node, list):
            return "".join(self.format_ast(item, indent) for item in node)
        res = f"{indent}└── [{node['type']}]"
        if 'target' in node: res += f" Name: {node['target']}"
        if 'value' in node and not isinstance(node['value'], dict): res += f" ➔ {node['value']}"
        res += "\n"
        child_indent = indent + "    "
        if 'value' in node and isinstance(node['value'], dict): res += self.format_ast(node['value'], child_indent)
        if 'left' in node:
            res += f"{child_indent}├── [Left]\n" + self.format_ast(node['left'], child_indent + "│   ")
            res += f"{child_indent}├── [Op]: {node['op']}\n"
            res += f"{child_indent}└── [Right]\n" + self.format_ast(node['right'], child_indent + "│   ")
        if 'condition' in node:
            res += f"{child_indent}├── [Condition]\n" + self.format_ast(node['condition'], child_indent + "│   ")
            res += f"{child_indent}└── [Body]\n"
            for b in node['body']: res += self.format_ast(b, child_indent + "    ")
        if 'arguments' in node:
            for a in node['arguments']: res += self.format_ast(a, child_indent)
        return res

    def compile_pipeline(self):
        code = self.code_editor.toPlainText()
        self.vars = {}
        self.exec_log.clear()
        try:
            tokens = lex(code)
            self.lexer_table.setRowCount(len(tokens))
            for i, (k, v) in enumerate(tokens):
                self.lexer_table.setItem(i, 0, QTableWidgetItem(k))
                self.lexer_table.setItem(i, 1, QTableWidgetItem(v))

            ast = Parser(tokens).parse()
            self.ast_view.setPlainText(self.format_ast(ast))

            tac_gen = TACGenerator()
            for n in ast: tac_gen.generate(n)
            self.tac_view.setPlainText("\n".join(tac_gen.instructions))

            logs = ["*** Execution Trace ***"]
            for n in ast: self.execute_node_gui(n, logs)
            self.exec_log.setPlainText("\n".join(logs))
            
            self.sym_table.setRowCount(len(self.vars))
            for i, (k, v) in enumerate(self.vars.items()):
                self.sym_table.setItem(i, 0, QTableWidgetItem(k))
                self.sym_table.setItem(i, 1, QTableWidgetItem(str(v)))
            self.tabs.setCurrentIndex(3)
        except Exception as e:
            self.exec_log.setPlainText(f"❌ COMPILER ERROR:\n{str(e)}")
            self.tabs.setCurrentIndex(3)

    def eval_expr_gui(self, expr, log):
        t = expr['type']
        if t == 'NUMBER': return int(expr['value'])
        if t == 'STRING': return expr['value'].strip('"')
        if t == 'ID':
            if expr['value'] in self.vars: return self.vars[expr['value']]
            raise NameError(f"Undefined: {expr['value']}")
        if t == 'BinaryOp':
            l, r = self.eval_expr_gui(expr['left'], log), self.eval_expr_gui(expr['right'], log)
            op = expr['op']
            res = eval(f"{repr(l)} {op} {repr(r)}")
            log.append(f"  [Math/Comp] {l} {op} {r} = {res}")
            return res

    def execute_node_gui(self, node, log):
        t = node['type']
        if t == 'Assignment':
            val = self.eval_expr_gui(node['value'], log)
            self.vars[node['target']] = val
            log.append(f"● MEMORY: {node['target']} ➔ {val}")
        elif t == 'Print':
            out = " ".join(str(self.eval_expr_gui(a, log)) for a in node['arguments'])
            log.append(f"▶ OUTPUT: {out}")
        elif t == 'IfStatement':
            res = self.eval_expr_gui(node['condition'], log)
            log.append(f"◆ IF CONDITION RESULT: {res}")
            if res:
                for s in node['body']: self.execute_node_gui(s, log)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CompilerApp()
    window.show()
    sys.exit(app.exec())