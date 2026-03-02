#!/usr/bin/env python3
"""
Threads毎日投稿スクリプト
AI/Salesforce/SaaSトレンドを収集し、Threads投稿案を生成・保存する

使用方法:
    export ANTHROPIC_API_KEY="sk-ant-..."
    .venv/bin/python daily_post.py
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic

# 日本標準時（JST）
JST = timezone(timedelta(hours=9))


def get_today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def build_prompt(today: str) -> str:
    return f"""あなたはAI・Salesforce・SaaS領域の深い知見を持つ専門家アシスタントです。
今日の日付は {today} です。以下の2ステップを順番に実行してください。

---

### 【ステップ1：最新トレンドの収集と選定】

以下の検索クエリで検索し、AI・Salesforce・SaaS業務改善に関する**本日最新の**ニュースを収集してください：

1. `site:news.ycombinator.com AI SaaS agents latest {today}`
2. `Salesforce Agentforce news announcement {today}`
3. `AI SaaS business automation breaking news {today}`

収集した情報から、**ビジネスインパクトが最も大きい・最も目新しい**トピックを1つだけ選定し、以下の形式でまとめてください：

🔥 本日のトピック：[タイトル]
ソース: [URL]
概要（1-2行）: [何が起きたか]
ビジネスインパクト: [なぜ重要か]

---

### 【ステップ2：Threads投稿案を1本作成】

選定したトピックで、以下のフォーマットで投稿案を1本だけ作成してください。
投稿案の前後に必ず「---THREADS POST 1---」と「---END---」を入れてください：

---THREADS POST 1---
【投稿タイトル（絵文字＋インパクトある一言）】

[フック：驚きの事実 or 共感を呼ぶ問いかけ（1-2行）]

[本文：専門的だがフランクなトーンで3-5段落。専門用語は噛み砕く]

[実務アクション：「→ 今日からできること」を2-3点]

[エンゲージメント質問：「あなたの会社ではどうしてる？」系の問いかけ]

#AI #Salesforce #SaaS #業務改善 #AIエージェント
---END---

**トーン要件：**
- 専門的かつフランクで読みやすい
- 驚き・共感・実用性のバランス
- 最後は必ず読者参加型の問いかけで締める"""


def extract_all_text(content_blocks) -> str:
    parts = []
    for block in content_blocks:
        if hasattr(block, "text") and block.text:
            parts.append(block.text)
    return "\n".join(parts)


def run(client: anthropic.Anthropic, today: str) -> str:
    messages = [{"role": "user", "content": build_prompt(today)}]
    tools = [{"type": "web_search_20250305", "name": "web_search"}]

    print("  トレンドを検索・分析中...", flush=True)

    # エージェンティックループ（web_search ツールの複数回呼び出しに対応）
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            messages=messages,
            tools=tools,
        )

        if response.stop_reason == "end_turn":
            return extract_all_text(response.content)

        if response.stop_reason == "tool_use":
            # アシスタントのメッセージを会話履歴に追加
            messages.append({"role": "assistant", "content": response.content})

            # web_search_20250305 の結果を tool_result として返す
            tool_results = []
            for block in response.content:
                if block.type == "tool_result":
                    # サーバーサイドで検索が実行済み → そのまま使用
                    pass
                elif block.type == "tool_use" and block.name == "web_search":
                    # フォールバック：ツール呼び出しに空の結果を返す
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Search executed server-side.",
                        }
                    )

            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            print("  検索結果を処理中...", flush=True)
            continue

        # 予期しない stop_reason の場合は現状のテキストを返す
        return extract_all_text(response.content)


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("エラー: 環境変数 ANTHROPIC_API_KEY が設定されていません。", file=sys.stderr)
        print("  export ANTHROPIC_API_KEY='sk-ant-...' を実行してください。", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    today = get_today_jst()

    print(f"[{today}] Threads投稿案の生成を開始します...")

    result = run(client, today)

    # 出力先ディレクトリを作成
    output_dir = Path(__file__).parent / "outputs"
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / f"threads-post-{today}.md"
    generated_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

    content = (
        f"# Threads投稿案 - {today}\n\n"
        f"生成日時: {generated_at}\n\n"
        "---\n\n"
        + result
    )

    output_file.write_text(content, encoding="utf-8")

    print(f"✅ 保存完了: {output_file}")
    print()
    print("--- プレビュー（先頭500文字）---")
    print(result[:500])
    print("...")


if __name__ == "__main__":
    main()
