"""Componenti visivi condivisi della dashboard Benessere."""
from html import escape
import streamlit as st

def apply_theme():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
    :root {color-scheme:dark}
    html,body,[data-testid="stApp"]{font-family:'DM Sans',sans-serif;background:#0b111d;color:#e6edf5}
    [data-testid="stAppViewContainer"]{background:radial-gradient(ellipse 1000px 440px at 90% -14%,#15364a 0%,transparent 66%),#0b111d}
    [data-testid="stHeader"]{background:transparent}
    .block-container{max-width:1240px;padding-top:1.4rem;padding-bottom:4rem}
    h1,h2,h3{font-family:'Manrope','DM Sans',sans-serif;letter-spacing:-.045em}
    h1{font-weight:800!important;font-size:clamp(1.7rem,3vw,2.55rem)!important}
    h2{font-size:1.5rem!important}
    h3{font-size:1.1rem!important}
    [data-testid="stMetric"]{background:rgba(18,29,45,.92);border:1px solid #283849;padding:1rem 1.1rem;border-radius:17px;min-height:112px}
    [data-testid="stMetricLabel"] p{font-size:.9rem;color:#a4b6c8}
    [data-testid="stMetricValue"]{font-family:'Manrope',sans-serif;font-weight:800;letter-spacing:-.05em}
    [data-testid="stMetricDelta"]{font-size:.8rem}
    div[data-testid="stVerticalBlock"]>div:has(>.ben-section){border:0}
    div[data-testid="stExpander"]{border:1px solid #2b3d50;border-radius:16px;background:#101b2b}
    [data-testid="stForm"]{background:rgba(18,29,45,.56);border:1px solid #2a3a4b;border-radius:18px;padding:1.25rem}
    [data-testid="stDataFrame"]{border:1px solid #24374a;border-radius:14px;overflow:hidden}
    div[data-testid="stAlert"]{border-radius:14px}
    .stButton>button[kind="primary"],[data-testid="stFormSubmitButton"]>button[kind="primary"]{background:linear-gradient(110deg,#54e3c6,#33b6c4);color:#07151c!important;border:0;border-radius:12px;font-weight:800;min-height:43px}
    .stButton>button:not([kind="primary"]){border-radius:12px;border-color:#33495b}
    div[data-testid="stRadio"] [role="radiogroup"]{gap:.34rem;display:flex;flex-wrap:wrap;padding:.35rem;border-radius:16px;background:#131f30;border:1px solid #28394c}
    div[data-testid="stRadio"] [role="radiogroup"] label{background:#182639;border:1px solid #334559;border-radius:12px;padding:.48rem .72rem;margin:0;min-height:40px}
    div[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked){background:#1a4d56;border-color:#44d5c2;color:#f5faff}
    div[data-testid="stRadio"] [role="radiogroup"] label p{font-size:.83rem;font-weight:700}
    .ben-kicker{color:#67decf;font-size:.78rem;font-weight:800;text-transform:uppercase;letter-spacing:.16em;margin:0 0 .45rem}
    .ben-hero{position:relative;overflow:hidden;background:linear-gradient(112deg,#17354a,#10313b 60%,#173b38);border:1px solid #2b5660;border-radius:22px;padding:1.65rem 1.8rem;margin-bottom:1rem}
    .ben-hero:after{content:'';position:absolute;right:-70px;top:-65px;width:245px;height:245px;border-radius:50%;background:radial-gradient(circle,#47d4bd33,transparent 65%);pointer-events:none}
    .ben-hero h1{margin:.1rem 0 .3rem;color:#f0fafc;font-size:clamp(1.9rem,4vw,2.7rem)!important}
    .ben-hero p{margin:0;color:#bfd9e2;font-size:.95rem}
    .ben-tag{display:inline-block;background:#23585b;color:#c7f8ec;border:1px solid #39766f;border-radius:30px;padding:.24rem .7rem;font-weight:700;font-size:.73rem}
    .ben-card{background:#121d2d;border:1px solid #273b4c;border-radius:17px;padding:1.05rem 1.2rem;margin-bottom:.72rem;overflow-wrap:anywhere}
    .ben-card-title{font-family:Manrope,sans-serif;color:#f1f6ff;font-weight:800;font-size:1.03rem}
    .ben-card-sub{color:#b1c2d1;font-size:.87rem;line-height:1.52;margin-top:.4rem}
    .ben-value{font-family:Manrope,sans-serif;font-size:1.55rem;font-weight:800;color:#6ce6cc}
    .ben-eyebrow{color:#8b9fb6;text-transform:uppercase;font-size:.72rem;letter-spacing:.11em;font-weight:800}
    .ben-empty{padding:1.25rem 1.45rem;border:1px dashed #416071;border-radius:16px;color:#b7c7d5;background:#11202c;margin:.6rem 0 1rem}
    .ben-section{margin-top:1.1rem;margin-bottom:.75rem}
    .ben-section b{font-family:Manrope,sans-serif;font-size:1.2rem;color:#e7f4fa}
    .ben-pills{display:flex;gap:.5rem;flex-wrap:wrap}
    .ben-pill{display:inline-block;background:#182e3e;border:1px solid #325365;border-radius:999px;color:#c9dbe6;padding:.35rem .7rem;font-size:.77rem;font-weight:700}
    .stProgress>div>div>div>div{background:#43d7bd}
    [data-testid="stTabs"] button{font-weight:700}
    input,textarea{font-size:16px!important}
    @media(max-width:700px){
      .block-container{padding:1rem .78rem 4rem!important}
      .ben-hero{padding:1.2rem 1.1rem;border-radius:17px}
      .ben-hero p{font-size:.85rem}
      .ben-card{padding:.95rem 1rem}
      [data-testid="stMetric"]{padding:.75rem .9rem;min-height:98px}
      [data-testid="stMetricValue"]{font-size:1.32rem}
      div[data-testid="stRadio"] [role="radiogroup"] label{padding:.34rem .55rem}
      div[data-testid="stRadio"] [role="radiogroup"] label p{font-size:.77rem}
      [data-testid="stForm"]{padding:.85rem}
    }
    @media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
    </style>
    """,unsafe_allow_html=True)

def hero(title: str, subtitle: str, *, kicker: str = "BENESSERE / DIARIO"):
    st.markdown(f'<div class="ben-hero"><div class="ben-kicker">{escape(kicker)}</div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>',unsafe_allow_html=True)

def section(title: str):
    st.markdown(f'<div class="ben-section"><b>{escape(title)}</b></div>',unsafe_allow_html=True)

def empty(message: str):
    st.markdown(f'<div class="ben-empty">{escape(message)}</div>',unsafe_allow_html=True)

def card(title: str, detail: str, caption: str = ""):
    label=f'<div class="ben-eyebrow">{escape(caption)}</div>' if caption else ''
    st.markdown(f'<div class="ben-card">{label}<div class="ben-card-title">{escape(title)}</div><div class="ben-card-sub">{escape(detail)}</div></div>',unsafe_allow_html=True)
