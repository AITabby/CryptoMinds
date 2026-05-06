.PHONY: test start stop clean lint install

# ── 安装 ──

install:
	pip install -r requirements.txt

# ── 测试 ──

test:
	python3 -m pytest tests/ -q

# ── 服务 ──

start:
	python3 src/api_server.py

stop:
	-pkill -f "api_server.py" 2>/dev/null

# ── 清理 ──

clean:
	rm -f *.log __pycache__/*.pyc
	rm -f .coverage htmlcov/
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# ── 代码检查 ──

lint:
	python3 -m flake8 --max-line-length=120 --exclude=node_modules,__pycache__,archive . 2>/dev/null || true

# ── SDK 构建 ──

build-python-sdk:
	cd sdk/python && python3 -m build

build-js-sdk:
	cd sdk/javascript && npm pack

# ── 发布 ──

publish-python:
	cd sdk/python && python3 -m twine upload dist/*

publish-js:
	cd sdk/javascript && npm publish