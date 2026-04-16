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
echo "=== Test Execute ==="
curl -s -m 5 -X POST http://localhost:5001/execute -H "Content-Type: application/json" -d '{"task":"test","request_id":"test-007"}'
echo ""
