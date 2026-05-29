from litellm.integrations.custom_logger import CustomLogger
from typing import Literal, Optional

class FlattenMCPTools(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data: dict, call_type: Literal["completion", "text_completion", "embeddings", "image_generation", "moderation", "audio_transcription"]) -> Optional[dict]:

        if call_type == "completion" and "tools" in data:
            print(f"\n[Proxy 攔截] 收到 {len(data['tools'])} 個工具，準備檢查...")
            new_tools = []
            modified = False

            for tool in data.get("tools", []):
                if tool.get("type") == "namespace":
                    modified = True
                    ns_name = tool.get("name", "")
                    print(f"  -> 發現 Namespace: '{ns_name}'，準備展開...")

                    for sub_tool in tool.get("tools", []):
                        if sub_tool.get("type") == "function":
                            original_name = sub_tool["function"]["name"]
                            new_name = f"{ns_name}{original_name}"
                            print(f"    -> 轉換工具名稱: {original_name} => {new_name}")
                            new_tools.append({
                                "type": "function",
                                "function": {
                                    "name": new_name,
                                    "description": sub_tool["function"].get("description", ""),
                                    "parameters": sub_tool["function"].get("parameters", {})
                                }
                            })
                else:
                    new_tools.append(tool)

            if modified:
                data["tools"] = new_tools
                print("[Proxy 攔截] 轉換完成！準備送給後端模型。\n")
            else:
                print("[Proxy 攔截] 未發現 Namespace，原樣放行。\n")

        return data

proxy_handler_instance = FlattenMCPTools()