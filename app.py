#!/usr/bin/env python3
"""
Threads毎日投稿 Web UI
ブラウザで生成・確認・コピーができるシンプルなUI
"""

import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import streamlit as st
import anthropic

JST = timezone(timedelta(hours=9))

st.set_page_config(
    page_title="Threads毎日投稿",
    page_icon="🧵",
    layout="wide",
)


# ─── ユーティリティ ─────────────────────────────────────────

def get_today() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def output_dir() -> Path:
    return Path(__file__).parent / "outputs"


def load_past_files() -> list[Path]:
    """outputs/ にある過去の投稿ファイルを新しい順で返す"""
    d = output_dir()
    d.mkdir(exist_ok=True)
    return sorted(d.glob("threads-post-*.md"), reverse=True)


def load_file(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    parts = raw.split("---\n\n", 1)
    return parts[1] if len(parts) > 1 else raw


def extract_posts(text: str) -> list[str]:
    """---THREADS POST n--- マーカーで投稿案を分割して抽出"""
    pattern = r"---THREADS POST \d+---(.*?)(?=---THREADS POST \d+---|---END---|$)"
    return [m.strip() for m in re.findall(pattern, text, re.DOTALL)]


def extract_sources(text: str) -> list[str]:
    """テキスト中の URL を重複なしで抽出"""
    urls = re.findall(r"https?://[^\s\)\]\"\'\u3000\u300d]+", text)
    seen, result = set(), []
    for u in urls:
        u = u.rstrip(".,;:")
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def build_prompt(today: str) -> str:
    # f-string 内で {n} をそのまま出力したいので {{ }} でエスケープ
    return f"""あなたはAI・Salesforce・SaaS領域の深い知見を持つ専門家アシスタントです。
今日の日付は {today} です。以下の3ステップを実行してください。

### 【ステップ1：最新トレンドの収集】
以下の検索クエリで検索し、AI・Salesforce・SaaS業務改善に関する本日最新のニュースを収集してください：
1. site:news.ycombinator.com AI SaaS agents latest {today}
2. Reddit r/artificial r/salesforce r/SaaS trending discussion {today}
3. Salesforce Agentforce news announcement {today}
4. AI SaaS business automation breaking news {today}
5. Hacker News top AI productivity enterprise {today}

### 【ステップ2：トップ3トピックのダイジェスト】
選定した3トピックを以下の形式でまとめてください：
🔥 Topic [番号]：[タイトル]
ソース: [URL（必ず記載）]
概要: [何が起きたか]
ビジネスインパクト: [なぜ重要か]
ダイジェスト（ニュースの核心・専門家の視点・実務への応用）

### 【ステップ3：Threads投稿案3本の作成】
各トピックについて以下の形式で投稿案を作成してください。
投稿案の区切りには必ず「---THREADS POST {{n}}---」(n=1,2,3) というマーカーを入れてください：

---THREADS POST 1---
【タイトル（絵文字＋インパクト）】

[フック：1-2行]

[本文：専門的だがフランクなトーン]

[→ 今日からできること：2-3点]

[エンゲージメント質問]

#AI #Salesforce #SaaS #業務改善 #AIエージェント
---THREADS POST 2---
（同様）
---THREADS POST 3---
（同様）
---END---"""


def generate(api_key: str, today: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": build_prompt(today)}]
    tools = [{"type": "web_search_20250305", "name": "web_search"}]

    full_text = ""
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            messages=messages,
            tools=tools,
        )
        for block in response.content:
            if hasattr(block, "text"):
                full_text += block.text

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = [
                {"type": "tool_result", "tool_use_id": b.id, "content": "Search executed."}
                for b in response.content
                if b.type == "tool_use" and b.name == "web_search"
            ]
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

    return full_text


def save_output(today: str, content: str) -> Path:
    d = output_dir()
    d.mkdir(exist_ok=True)
    path = d / f"threads-post-{today}.md"
    generated_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    path.write_text(
        f"# Threads投稿案 - {today}\n\n生成日時: {generated_at}\n\n---\n\n{content}",
        encoding="utf-8",
    )
    return path


# ─── サイドバー ─────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 設定")
    # Streamlit Cloud の Secrets → 環境変数 → 手入力 の順で読み込む
    env_key = (
        st.secrets.get("ANTHROPIC_API_KEY", "")
        if hasattr(st, "secrets")
        else os.environ.get("ANTHROPIC_API_KEY", "")
    )
    api_key = st.text_input(
        "Anthropic API Key",
        value=env_key,
        type="password",
        placeholder="sk-ant-...",
    )

    st.divider()

    # 過去の投稿一覧
    st.subheader("📂 過去の投稿一覧")
    past_files = load_past_files()
    if past_files:
        labels = [p.stem.replace("threads-post-", "") for p in past_files]
        selected_label = st.radio(
            "日付を選択",
            options=labels,
            index=0,
            label_visibility="collapsed",
        )
        selected_file = past_files[labels.index(selected_label)]
    else:
        st.caption("まだ投稿がありません")
        selected_file = None
        selected_label = None


# ─── session_state 初期化 ──────────────────────────────────
if "loaded_date" not in st.session_state:
    st.session_state.loaded_date = None
if "content" not in st.session_state:
    st.session_state.content = None
if "posts" not in st.session_state:
    st.session_state.posts = []
if "sources" not in st.session_state:
    st.session_state.sources = []


# ─── サイドバーで別の日付を選択したら読み込み直す ──────────
if selected_file and selected_label != st.session_state.loaded_date:
    raw = load_file(selected_file)
    st.session_state.content = raw
    st.session_state.posts = extract_posts(raw)
    st.session_state.sources = extract_sources(raw)
    st.session_state.loaded_date = selected_label


# ─── メイン画面 ────────────────────────────────────────────
st.title("🧵 Threads毎日投稿ジェネレーター")
st.caption("AI/Salesforce/SaaSトレンドから今日の投稿案を自動生成します")

today = get_today()
st.info(f"📅 今日の日付（JST）: **{today}**")

col_btn, col_status = st.columns([2, 5])
with col_btn:
    generate_btn = st.button(
        "🚀 今日の投稿案を生成する",
        type="primary",
        use_container_width=True,
        disabled=not api_key,
    )

if not api_key:
    st.warning("サイドバーでAPI Keyを入力してください")

# 今日分がまだ未生成なら今日のファイルを自動ロード
today_path = output_dir() / f"threads-post-{today}.md"
if today_path.exists() and st.session_state.loaded_date != today:
    raw = load_file(today_path)
    st.session_state.content = raw
    st.session_state.posts = extract_posts(raw)
    st.session_state.sources = extract_sources(raw)
    st.session_state.loaded_date = today
    with col_status:
        st.success(f"✅ 本日分を読み込みました（{today_path.name}）")

# 生成ボタン
if generate_btn and api_key:
    with st.spinner("🔍 Web検索中・投稿案を生成中… （1〜2分かかります）"):
        try:
            content = generate(api_key, today)
            path = save_output(today, content)
            st.session_state.content = content
            st.session_state.posts = extract_posts(content)
            st.session_state.sources = extract_sources(content)
            st.session_state.loaded_date = today
            with col_status:
                st.success(f"✅ 生成完了・保存しました: `{path.name}`")
            st.rerun()
        except Exception as e:
            st.error(f"エラー: {e}")


# ─── 表示エリア ─────────────────────────────────────────────
if st.session_state.posts:
    # 表示中の日付
    if st.session_state.loaded_date:
        st.subheader(f"📅 {st.session_state.loaded_date} の投稿案")

    # ── ソース一覧 ──────────────────────────────────────────
    if st.session_state.sources:
        with st.expander(f"🔗 参照ソース一覧（{len(st.session_state.sources)} 件）", expanded=True):
            for i, url in enumerate(st.session_state.sources, 1):
                st.markdown(f"{i}. [{url}]({url})")

    st.divider()

    # ── 投稿案（タブ） ──────────────────────────────────────
    st.subheader("📱 Threads投稿案")
    st.caption("テキストエリアで編集 → 全選択してコピー → Threadsへ貼り付け")

    tab_labels = [f"投稿案 {i+1}" for i in range(len(st.session_state.posts))]
    tabs = st.tabs(tab_labels)
    for i, (tab, post) in enumerate(zip(tabs, st.session_state.posts), 1):
        with tab:
            edited = st.text_area(
                f"post_{i}",
                value=post,
                height=420,
                key=f"post_{i}_{st.session_state.loaded_date}",
                label_visibility="collapsed",
            )
            st.caption(f"文字数: {len(edited)} 文字")

    st.divider()

    # ── 全文（ダイジェスト込み）──────────────────────────────
    with st.expander("📄 全文（ダイジェスト含む）を見る"):
        st.markdown(st.session_state.content)

else:
    st.markdown(
        """
        ### 使い方
        1. サイドバーに **Anthropic API Key** を入力
        2. **「🚀 今日の投稿案を生成する」** ボタンをクリック
        3. 3本の投稿案をコピーしてThreadsへ投稿
        4. 過去の投稿はサイドバーの **「過去の投稿一覧」** から確認できます
        """
    )
