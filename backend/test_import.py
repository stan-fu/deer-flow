import sys
sys.path.insert(0, '/Users/cooper/workload/deer-flow/backend/.venv/lib/python3.12/site-packages')

from langchain.agents.middleware import AgentMiddleware, SummarizationMiddleware

print(f"AgentMiddleware: {AgentMiddleware}")
print(f"SummarizationMiddleware: {SummarizationMiddleware}")
print(f"AgentMiddleware module: {AgentMiddleware.__module__}")