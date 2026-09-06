from litellm.integrations.custom_logger import CustomLogger
from typing import Literal, Optional
import json

class FlattenMCPTools(CustomLogger):
    # async def async_pre_call_hook(self, user_api_key_dict, cache, data: dict, call_type: Literal["completion", "text_completion", "embeddings", "image_generation", "moderation", "audio_transcription"]) -> Optional[dict]:

    #     print("=========")
    #     print(call_type)
    #     print("=========")
    #     # call_type == "completion" and
    #     if "tools" in data:
    #         print(f"\n[Proxy 攔截] 收到 {len(data['tools'])} 個工具，準備檢查...")
    #         new_tools = []
    #         modified = False

    #         for tool in data.get("tools", []):
    #             if tool.get("type") == "namespace":
    #                 modified = True
    #                 ns_name = tool.get("name", "")
    #                 if "mcp" not in ns_name:
    #                     continue
    #                 print(f"  -> 發現 Namespace: '{ns_name}'，準備展開...")

    #                 for sub_tool in tool.get("tools", []):
    #                     if sub_tool.get("type") == "function":
    #                         func = sub_tool.get("function") or sub_tool
    #                         original_name = func.get("name", sub_tool.get("name", ""))
    #                         new_name = f"{ns_name}__{original_name}"
    #                         print(f"    -> 轉換工具名稱: {original_name} => {new_name}")
    #                         new_tools.append({
    #                             "type": "function",
    #                             "function": {
    #                                 "name": new_name,
    #                                 "description": func.get("description", ""),
    #                                 "parameters": func.get("parameters", {})
    #                             }
    #                         })
    #             else:
    #                 new_tools.append(tool)

    #         if modified:
    #             data["tools"] = new_tools
    #             print("[Proxy 攔截] 轉換完成！準備送給後端模型。\n")
    #         else:
    #             print("[Proxy 攔截] 未發現 Namespace，原樣放行。\n")

    #     return data
    # 1. 攔截去程 (Request)
    async def async_pre_call_hook(self, user_api_key_dict, cache, data: dict, call_type: str) -> Optional[dict]:
        if "tools" in data and isinstance(data["tools"], list):
            print("\n=== [1. Proxy 攔截去程請求] ===")
            new_tools = []
            for tool in data["tools"]:
                # 1. 處理 Codex 的 Namespace 格式 (你的 MCP 工具)
                if tool.get("type") == "namespace":
                    ns_name = tool.get("name", "")
                    for sub_tool in tool.get("tools", []):
                        if sub_tool.get("type") == "function":
                            # 關鍵修正：使用 .copy() 完整保留 parameters, description 等所有屬性
                            func = sub_tool.get("function") or sub_tool
                            func_data = func.copy()
                            original_name = func_data.get("name", "")
                            if "mcp" in ns_name:
                                func_data["name"] = f"{ns_name}__{original_name}"
                            else:
                                func_data["name"] = f"{ns_name}{original_name}"
                            new_tools.append({
                                "type": "function",
                                "function": func_data
                            })
                # 2. 已經是標準 OpenAI 格式
                elif tool.get("type") == "function" and "function" in tool:
                    new_tools.append(tool)
                # 3. 修復 Anthropic 格式 (有 name 和 input_schema，但沒有 type="function")
                elif "name" in tool and ("input_schema" in tool or "parameters" in tool):
                    fixed_name = tool.get("name")
                    print(f"🔧 自動修復非標準工具格式: {fixed_name}")
                    new_tools.append({
                        "type": "function",
                        "function": {
                            "name": fixed_name,
                            "description": tool.get("description", ""),
                            "parameters": tool.get("input_schema", tool.get("parameters", {}))
                        }
                    })

                # 4. 其他未知或特規格式 (Anthropic Computer Use 等) -> 攔截並丟棄！
                else:
                    print(f"⚠️ 攔截到可能導致 vLLM 崩潰的異常工具，已將其過濾不傳送！")
                    print(f"異常工具內容: {json.dumps(tool, ensure_ascii=False, indent=2)}")

            data["tools"] = new_tools

            # 印出最終檢查清單
            final_tool_names = [t.get('function', {}).get('name') for t in new_tools]
            print(f"✅ 最終送給 vLLM 的安全工具列表: {final_tool_names}")
            print("===============================\n")
        return data

    # 2. 攔截回程 (Response) - 看看模型到底回了什麼！
    async def async_success_hook(self, data, user_api_key_dict, response):
        print("\n=== [2. Proxy 收到 LLM 回應] ===")
        try:
            if hasattr(response, 'choices') and len(response.choices) > 0:
                msg = response.choices[0].message
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tc in msg.tool_calls:
                        print(f"✅ 模型成功發動工具呼叫: {tc.function.name}")
                        print(f"📦 參數: {tc.function.arguments}")
                else:
                    print(f"❌ 模型沒有呼叫工具，回傳了純文字: {msg.content}")
        except Exception as e:
            print(f"解析回應時發生錯誤: {e}")
        print("================================\n")
        return response

proxy_handler_instance = FlattenMCPTools()