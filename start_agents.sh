#!/bin/bash
cd /Users/aitabby/projects/cryptominds
pkill -f "agent_server.py" 2>/dev/null
sleep 1
export CRYPTOMINDS_DEMO=1
python3 agents/agent_server.py --agent tiedan --port 5001 &
python3 agents/agent_server.py --agent choudan --port 5002 &
python3 agents/agent_server.py --agent ludan --port 5003 &
sleep 3
echo "=== Health Check ==="
curl -s http://localhost:5001/health
echo ""
curl -s http://localhost:5002/health
echo ""
curl -s http://localhost:5003/health
echo ""
echo "=== Test ExecuteOrder ==="
curl -s -m 10 -X POST http://localhost:5001/executeOrder -H "Content-Type: application/json" -d '{"action":"executeOrder","orderId":"test-001","sellerName":"tiedan","buyerWallet":"0xce0DE97496c20Dd773d75F560d3e4494cF542d96","amount":0.001,"currency":"BNB"}'
echo ""
