"""图片预览兜底工具。

部分格式（如 heic）浏览器原生渲染支持差，Streamlit 在按路径渲染时也可能因
PIL 无法解码而抛异常。此处捕获异常并退回文件名占位，避免整页崩溃。
"""
import os

import streamlit as st


def safe_image(path, **kwargs):
    """等价于 st.image(path, **kwargs)，但渲染失败时退回文件名占位而非抛错。"""
    try:
        st.image(path, **kwargs)
    except Exception:  # noqa: BLE001 - 渲染兜底：heic/损坏等任意解码失败均不致命
        st.caption(os.path.basename(path))
