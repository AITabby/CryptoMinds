.PHONY: test pytest node-test e2e start stop demo clean lint

# ── 测试 ──

test: pytest node-test
	@echo "All tests complete."

pytest:
	python3 -m pytest tests/ -q

node-test:
	cd web && npm test 2>/dev/null || echo "No Node.js tests configured"

e2e:
	python3 scripts/e2e_test.py

# ── 服务 ──

start: stop
	@echo "Starting CryptoMinds services..."
	bash web/start_services.sh

stop:
	-pkill -f "api_server.py" 2>/dev/null
	-pkill -f "server_modular.js" 2>/dev/null
	-pkill -f "start_agents.sh" 2>/dev/null

demo: stop
	@echo "Starting in DEMO mode..."
	bash demo.sh

# ── 清理 ──

clean:
	rm -f web/cryptominds.db web/*.log __pycache__/*.pyc
	rm -f .coverage htmlcov/
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# ── 代码检查 ──

lint:
	python3 -m flake8 --max-line-length=120 --exclude=node_modules,__pycache__,web/node_modules . 2>/dev/null || true

# ── 合约 ──

deploy-escrow:
	node scripts/deploy_service_escrow.js

# ── 数据库迁移 ──

migrate:
	cd web && node migrate_to_sqlite.js