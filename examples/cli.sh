afs run bignickeye/agentgym:textcraft-v2 --name textcraft

afs call textcraft evaluate --arg ids=[10] --arg model="deepseek-ai/DeepSeek-V3" --arg base_url="https://llm.chutes.ai/v1" --arg seed=2717596881

afs run bignickeye/agentgym:webshop-v2 --name webshop

afs call webshop evaluate --arg ids=[10] --arg model="deepseek-ai/DeepSeek-V3" --arg base_url="https://llm.chutes.ai/v1" --arg seed=2717596881

afs run bignickeye/affine:v2 --name affine

afs call affine evaluate --arg model="deepseek-ai/DeepSeek-V3" --arg base_url="https://llm.chutes.ai/v1" --arg seed=2717596881 --arg task_type=abd --arg num_samples=1
