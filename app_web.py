import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth
import os
import ccxt
import pandas as pd
from datetime import datetime, timezone, timedelta
import calendar
import requests
import base64
import json

# 페이지 설정 (모바일 최적화 레이아웃)
st.set_page_config(
    page_title="BINANCE | 선물 대시보드",
    page_icon="🟡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 다크 모드 및 스타일 적용
st.markdown("""
    <style>
    .main { background-color: #0b0e11; color: #eaecef; }
    .stMetric { background-color: #181a20; padding: 15px; border-radius: 8px; border: 1px solid #2b313a; }
    </style>
""", unsafe_allow_html=True)

# Firebase 초기화
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        if os.path.exists("firebase_key.json"):
            cred = credentials.Certificate("firebase_key.json")
            firebase_admin.initialize_app(cred)
            with open("firebase_key.json", "r", encoding="utf-8") as f:
                key_data = json.load(f)
                return firestore.client(), key_data.get("web_api_key", None)
    return None, None

db, firebase_web_api_key = init_firebase()

# 세션 상태 초기화
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_uid = None
    st.session_state.user_email = None
    st.session_state.api_key = ""
    st.session_state.api_secret = ""
    st.session_state.monthly_goal_krw = 1000000.0
    st.session_state.cal_year = datetime.now().year
    st.session_state.cal_month = datetime.now().month

# 환율 조회 함수 (업비트 API)
@st.cache_data(ttl=15)
def get_usdt_krw():
    try:
        r = requests.get("https://api.upbit.com/v1/ticker?markets=KRW-USDT", timeout=2).json()
        return float(r[0]['trade_price'])
    except Exception:
        return 1366.00

usdt_krw = get_usdt_krw()

# --- 🔐 로그인 / 회원가입 화면 ---
if not st.session_state.logged_in:
    st.title("🔑 BINANCE | 파이어베이스 로그인")
    st.markdown("외출 중에도 스마트폰으로 바이낸스 계정 상태를 실시간 모니터링하세요.")

    tab_login, tab_signup = st.tabs(["로그인", "회원가입"])

    with tab_login:
        with st.form("login_form"):
            email_input = st.text_input("이메일 (Email)", key="login_email")
            pw_input = st.text_input("비밀번호 (Password)", type="password", key="login_pw")
            submit_btn = st.form_submit_button("로그인")

            if submit_btn:
                if not email_input or not pw_input:
                    st.warning("이메일과 비밀번호를 모두 입력해주세요.")
                else:
                    if not firebase_web_api_key:
                        st.session_state.logged_in = True
                        st.session_state.user_uid = "local_user"
                        st.session_state.user_email = email_input
                        st.rerun()
                    else:
                        try:
                            url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_web_api_key}"
                            payload = {"email": email_input, "password": pw_input, "returnSecureToken": True}
                            resp = requests.post(url, json=payload, timeout=7)
                            res_data = resp.json()

                            if resp.status_code != 200 or "error" in res_data:
                                st.error("로그인 실패: 이메일 또는 비밀번호가 올바르지 않습니다.")
                            else:
                                st.session_state.logged_in = True
                                st.session_state.user_uid = res_data.get("localId")
                                st.session_state.user_email = res_data.get("email")
                                
                                if db:
                                    doc_ref = db.collection('users').document(st.session_state.user_uid).collection('settings').document('config')
                                    doc = doc_ref.get()
                                    if doc.exists:
                                        d = doc.to_dict()
                                        if d.get("key"):
                                            st.session_state.api_key = base64.b64decode(d.get("key")).decode("utf-8")
                                        if d.get("secret"):
                                            st.session_state.api_secret = base64.b64decode(d.get("secret")).decode("utf-8")
                                        if "monthly_goal_krw" in d:
                                            st.session_state.monthly_goal_krw = float(d.get("monthly_goal_krw"))
                                st.success(f"반갑습니다, {st.session_state.user_email}님!")
                                st.rerun()
                        except Exception as e:
                            st.error(f"서버 통신 오류: {e}")

    with tab_signup:
        with st.form("signup_form"):
            signup_email = st.text_input("새 이메일 (Email)", key="signup_email")
            signup_pw = st.text_input("새 비밀번호 (6자리 이상)", type="password", key="signup_pw")
            signup_btn = st.form_submit_button("회원가입")

            if signup_btn:
                if not signup_email or not signup_pw:
                    st.warning("이메일과 비밀번호를 모두 입력해주세요.")
                elif len(signup_pw) < 6:
                    st.warning("비밀번호는 최소 6자리 이상이어야 합니다.")
                else:
                    try:
                        if db:
                            auth.create_user(email=signup_email, password=signup_pw)
                            st.success("회원가입 완료! 로그인 탭에서 로그인해 주세요.")
                        else:
                            st.info("로컬 모드로 가입되었습니다.")
                    except Exception as e:
                        st.error(f"회원가입 실패: {e}")
    st.stop()

# --- 📊 메인 네비게이션 및 사이드바 ---
st.sidebar.title(f"👤 {st.session_state.user_email}")

if st.sidebar.button("🔄 데이터 즉시 동기화"):
    st.rerun()

if st.sidebar.button("로그아웃"):
    st.session_state.logged_in = False
    st.session_state.user_uid = None
    st.session_state.user_email = None
    st.rerun()

menu = st.sidebar.radio("📌 메뉴 선택", ["📊 계좌 현황 & 포지션", "📅 PnL 월간 히트맵", "🏆 유저 PnL 랭킹", "⚙️ 바이낸스 API 설정"])

# 1. 바이낸스 API 설정 탭
if menu == "⚙️ 바이낸스 API 설정":
    st.subheader("⚙️ 바이낸스 Futures API 연동")
    st.markdown("바이낸스 계정의 실시간 자산 및 포지션을 조회하기 위한 API 키를 입력하세요.")

    with st.form("api_form"):
        input_key = st.text_input("API Key", value=st.session_state.api_key, type="password")
        input_secret = st.text_input("Secret Key", value=st.session_state.api_secret, type="password")
        input_goal = st.number_input("월간 목표 PnL (KRW)", value=int(st.session_state.monthly_goal_krw), step=100000)
        save_api_btn = st.form_submit_button("설정 저장 및 연동")

        if save_api_btn:
            st.session_state.api_key = input_key
            st.session_state.api_secret = input_secret
            st.session_state.monthly_goal_krw = float(input_goal)
            
            if db and st.session_state.user_uid:
                try:
                    enc_key = base64.b64encode(input_key.encode("utf-8")).decode("utf-8")
                    enc_secret = base64.b64encode(input_secret.encode("utf-8")).decode("utf-8")
                    doc_ref = db.collection('users').document(st.session_state.user_uid).collection('settings').document('config')
                    doc_ref.set({
                        'email': st.session_state.user_email,
                        'key': enc_key,
                        'secret': enc_secret,
                        'monthly_goal_krw': st.session_state.monthly_goal_krw,
                        'updated_at': firestore.SERVER_TIMESTAMP
                    }, merge=True)
                    st.success("API 키가 안전하게 저장 및 연동되었습니다!")
                except Exception as e:
                    st.error(f"저장 중 오류 발생: {e}")

# 2. 계좌 현황 & 포지션 탭
elif menu == "📊 계좌 현황 & 포지션":
    st.subheader("💼 선물 계좌 실시간 현황")

    total_asset_krw = 0.0
    total_asset_usdt = 0.0
    unpnl_krw = 0.0
    unpnl_usdt = 0.0
    today_pnl_krw = 0.0
    today_pnl_usdt = 0.0
    positions = []

    if st.session_state.api_key and st.session_state.api_secret:
        try:
            exchange = ccxt.binance({
                'apiKey': st.session_state.api_key,
                'secret': st.session_state.api_secret,
                'options': {
                    'defaultType': 'future',
                    'adjustForTimeDifference': True,
                    'recvWindow': 60000,
                },
                'enableRateLimit': True
            })
            exchange.load_time_difference()
            balance = exchange.fetch_balance()
            wallet_balance = float(balance['info']['totalWalletBalance'])
            
            pos_data = exchange.fetch_positions()
            for p in pos_data:
                size = float(p['contracts'])
                if size > 0:
                    symbol = p['symbol']
                    side = "롱" if p['side'] == 'long' else "숏"
                    entry = float(p['entryPrice'])
                    mark = float(p['markPrice'])
                    pnl = float(p['unrealizedPnl'])
                    unpnl_usdt += pnl
                    margin = float(p['initialMargin'])
                    r_pct = (pnl / margin * 100) if margin > 0 else 0
                    liq_price = float(p.get('liquidationPrice', 0) or 0)
                    
                    positions.append({
                        "종목 / 방향": f"{symbol} ({side})",
                        "수량": f"{size:.4f}",
                        "진입가 (USDT)": f"${entry:,.2f}",
                        "현재가 (USDT)": f"${mark:,.2f}",
                        "레버리지": f"{p.get('leverage', 1)}x",
                        "청산가": f"{liq_price:,.2f}" if liq_price > 0 else "N/A",
                        "증거금 (KRW)": f"₩ {margin * usdt_krw:,.0f}",
                        "미실현 PNL (KRW)": f"₩ {pnl * usdt_krw:,.0f}",
                        "수익률": f"{'+' if r_pct>=0 else ''}{r_pct:.2f}%"
                    })

            now_utc = datetime.now(timezone.utc)
            start_of_today_utc = datetime(now_utc.year, now_utc.month, now_utc.day, 0, 0, 0, tzinfo=timezone.utc)
            start_ts = int(start_of_today_utc.timestamp() * 1000)
            
            try:
                incomes = exchange.fapiPrivateGetIncome({'startTime': start_ts, 'limit': 1000})
                for item in incomes:
                    if int(item.get('time', 0)) >= start_ts:
                        if item.get('incomeType') in ['REALIZED_PNL', 'COMMISSION']:
                            today_pnl_usdt += float(item.get('income', 0))
            except Exception:
                pass

            total_asset_usdt = wallet_balance + unpnl_usdt
            total_asset_krw = total_asset_usdt * usdt_krw
            unpnl_krw = unpnl_usdt * usdt_krw
            today_pnl_krw = today_pnl_usdt * usdt_krw

        except Exception as e:
            st.error(f"바이낸스 연동 오류 (API Key를 확인하세요): {e}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="💼 현재 총 자산 (KRW)", value=f"₩ {total_asset_krw:,.0f}", delta=f"≈ ${total_asset_usdt:,.2f}")
    with col2:
        st.metric(label="📈 미실현 PNL (KRW)", value=f"₩ {unpnl_krw:,.0f}", delta=f"≈ ${unpnl_usdt:,.2f}")
    with col3:
        st.metric(label="💰 오늘 실현손익 (KRW)", value=f"₩ {today_pnl_krw:,.0f}", delta=f"≈ ${today_pnl_usdt:,.2f}")

    st.markdown("---")
    st.subheader("📊 열린 포지션")
    if positions:
        st.dataframe(pd.DataFrame(positions), use_container_width=True)
    else:
        st.info("현재 열려 있는 포지션이 없거나 바이낸스 API가 연동되지 않았습니다.")

# 3. PnL 월간 히트맵 탭 (선택한 연도/월의 실제 바이낸스 데이터만 엄격하게 조회)
elif menu == "📅 PnL 월간 히트맵":
    st.subheader("📅 PnL 월간 히트맵 & 챌린지")

    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([1, 2, 1, 2])
    
    with ctrl_col1:
        if st.button("◀ 지난달"):
            if st.session_state.cal_month == 1:
                st.session_state.cal_month = 12
                st.session_state.cal_year -= 1
            else:
                st.session_state.cal_month -= 1
            st.rerun()
            
    with ctrl_col2:
        st.markdown(f"### **{st.session_state.cal_year}년 {st.session_state.cal_month:02d}월**")
        
    with ctrl_col3:
        if st.button("다음달 ▶"):
            if st.session_state.cal_month == 12:
                st.session_state.cal_month = 1
                st.session_state.cal_year += 1
            else:
                st.session_state.cal_month += 1
            st.rerun()

    with ctrl_col4:
        new_goal = st.number_input("🎯 목표 PnL (₩)", value=int(st.session_state.monthly_goal_krw), step=100000)
        if new_goal != st.session_state.monthly_goal_krw:
            st.session_state.monthly_goal_krw = float(new_goal)

    st.markdown("---")

    daily_pnl = {}
    if st.session_state.api_key and st.session_state.api_secret:
        try:
            exchange = ccxt.binance({
                'apiKey': st.session_state.api_key,
                'secret': st.session_state.api_secret,
                'options': {
                    'defaultType': 'future',
                    'adjustForTimeDifference': True,
                    'recvWindow': 60000,
                },
                'enableRateLimit': True
            })
            exchange.load_time_difference()

            start_dt = datetime(st.session_state.cal_year, st.session_state.cal_month, 1, 0, 0, 0, tzinfo=timezone.utc)
            if st.session_state.cal_month == 12:
                end_dt = datetime(st.session_state.cal_year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            else:
                end_dt = datetime(st.session_state.cal_year, st.session_state.cal_month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)

            start_ts = int(start_dt.timestamp() * 1000)
            end_ts = int(end_dt.timestamp() * 1000)

            incomes = exchange.fapiPrivateGetIncome({'startTime': start_ts, 'endTime': end_ts, 'limit': 1000})
            for item in incomes:
                inc_type = item.get('incomeType')
                if inc_type in ['REALIZED_PNL', 'COMMISSION', 'FUNDING_FEE']:
                    amount = float(item.get('income', 0))
                    item_time = int(item.get('time', 0)) / 1000.0
                    item_dt = datetime.fromtimestamp(item_time, tz=timezone.utc) + timedelta(hours=9)
                    
                    # 👈 선택한 연도와 월에 정확히 일치하는 내역만 필터링
                    if item_dt.year == st.session_state.cal_year and item_dt.month == st.session_state.cal_month:
                        d = item_dt.day
                        daily_pnl[d] = daily_pnl.get(d, 0.0) + amount

            # 선택한 월의 문서에 정확히 동기화 (기존 잘못된 데이터 덮어쓰기 방지를 위해 명확히 초기화 후 저장)
            if db and st.session_state.user_uid:
                doc_id = f"{st.session_state.cal_year}_{st.session_state.cal_month:02d}"
                doc_ref = db.collection('users').document(st.session_state.user_uid).collection('monthly_pnl').document(doc_id)
                sum_pnl_usdt = sum(daily_pnl.values())
                
                doc_ref.set({
                    'year': st.session_state.cal_year,
                    'month': st.session_state.cal_month,
                    'daily_pnl': {str(k): v for k, v in daily_pnl.items()},
                    'total_month_usdt': sum_pnl_usdt,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })

        except Exception as e:
            st.warning(f"바이낸스 실시간 데이터 연동 중 오류 (API 키 확인): {e}")
            if db and st.session_state.user_uid:
                try:
                    doc_id = f"{st.session_state.cal_year}_{st.session_state.cal_month:02d}"
                    doc_ref = db.collection('users').document(st.session_state.user_uid).collection('monthly_pnl').document(doc_id)
                    doc = doc_ref.get()
                    if doc.exists:
                        data = doc.to_dict()
                        if data.get('year') == st.session_state.cal_year and data.get('month') == st.session_state.cal_month:
                            daily_pnl = {int(k): float(v) for k, v in data.get('daily_pnl', {}).items()}
                except Exception:
                    pass
    else:
        if db and st.session_state.user_uid:
            try:
                doc_id = f"{st.session_state.cal_year}_{st.session_state.cal_month:02d}"
                doc_ref = db.collection('users').document(st.session_state.user_uid).collection('monthly_pnl').document(doc_id)
                doc = doc_ref.get()
                if doc.exists:
                    data = doc.to_dict()
                    if data.get('year') == st.session_state.cal_year and data.get('month') == st.session_state.cal_month:
                        daily_pnl = {int(k): float(v) for k, v in data.get('daily_pnl', {}).items()}
            except Exception as e:
                st.error(f"히트맵 데이터를 불러오는 중 오류 발생: {e}")

    tot_m_usdt = sum(daily_pnl.values())
    tot_m_krw = tot_m_usdt * usdt_krw
    win_days = sum(1 for v in daily_pnl.values() if v > 0)
    trade_days = len(daily_pnl)
    win_rate = (win_days / trade_days * 100) if trade_days > 0 else 0.0
    max_win_usdt = max(daily_pnl.values(), default=0.0) if daily_pnl else 0.0

    goal = max(st.session_state.monthly_goal_krw, 1.0)
    pct = (tot_m_krw / goal) * 100
    
    st.markdown(f"🎯 **이번 달 목표 달성률** (목표 ₩{goal:,.0f} / 현재 ₩{tot_m_krw:,.0f} - **{pct:.1f}%**)")
    st.progress(max(0.0, min(pct / 100.0, 1.0)))

    st.markdown("---")

    cal_mat = calendar.monthcalendar(st.session_state.cal_year, st.session_state.cal_month)
    days_name = ["일 (SUN)", "월 (MON)", "화 (TUE)", "수 (WED)", "목 (THU)", "금 (FRI)", "토 (SAT)"]
    
    cols = st.columns(7)
    for idx, d_name in enumerate(days_name):
        cols[idx].markdown(f"<div style='text-align: center; font-weight: bold;'>{d_name}</div>", unsafe_allow_html=True)

    for week in cal_mat:
        w_cols = st.columns(7)
        for col_idx, day in enumerate(week):
            with w_cols[col_idx]:
                if day == 0:
                    st.markdown("<div style='height: 70px;'></div>", unsafe_allow_html=True)
                else:
                    pnl_usdt = daily_pnl.get(day, None)
                    if pnl_usdt is not None:
                        pnl_krw = pnl_usdt * usdt_krw
                        bg_color = "#006400" if pnl_usdt > 0 else "#8B0000"
                        sign = "+" if pnl_krw >= 0 else ""
                        st.markdown(f"""
                            <div style='background-color: {bg_color}; padding: 8px; border-radius: 5px; text-align: center; height: 75px;'>
                                <div style='font-size: 11px; font-weight: bold;'>{day}</div>
                                <div style='font-size: 10px; color: #fff;'>{sign}{pnl_krw:,.0f}원</div>
                            </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                            <div style='background-color: #181a20; border: 1px solid #2b313a; padding: 8px; border-radius: 5px; text-align: center; height: 75px;'>
                                <div style='font-size: 11px; color: #848e9c;'>{day}</div>
                            </div>
                        """, unsafe_allow_html=True)

    st.markdown("---")

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("월간 총 손익 (KRW)", f"₩ {tot_m_krw:,.0f}")
    with m2:
        st.metric("월간 총 손익 (USDT)", f"$ {tot_m_usdt:,.2f}")
    with m3:
        st.metric("수익 일수 / 승률", f"{win_days}일 / {trade_days}일 ({win_rate:.1f}%)")
    with m4:
        st.metric("🔥 연속 수익 Streak", f"현재 {win_days}일")
    with m5:
        st.metric("최대 일일 수익", f"₩ {max_win_usdt * usdt_krw:,.0f}")

# 4. 유저 PnL 랭킹 탭
elif menu == "🏆 유저 PnL 랭킹":
    st.subheader("🏆 실시간 유저 PnL 리더보드")
    
    if db:
        try:
            docs = db.collection('public_ranking').stream()
            users_list = []
            for doc in docs:
                d = doc.to_dict()
                users_list.append({
                    '유저': d.get('email', 'unknown'),
                    '누적 수익 (USDT)': float(d.get('total_pnl_usdt', 0.0)),
                    '오늘 수익 (USDT)': float(d.get('today_pnl_usdt', 0.0))
                })
            
            if users_list:
                df = pd.DataFrame(users_list)
                
                st.markdown("### 🔥 누적(월간) PnL 순위 TOP")
                df_tot = df.sort_values(by="누적 수익 (USDT)", ascending=False).reset_index(drop=True)
                df_tot.index += 1
                st.dataframe(df_tot, use_container_width=True)

                st.markdown("### ⚡ 오늘(일별) PnL 순위 TOP")
                df_today = df.sort_values(by="오늘 수익 (USDT)", ascending=False).reset_index(drop=True)
                df_today.index += 1
                st.dataframe(df_today, use_container_width=True)
            else:
                st.warning("등록된 랭킹 데이터가 없습니다.")
        except Exception as e:
            st.error(f"랭킹 데이터를 불러오는 중 오류 발생: {e}")
    else:
        st.error("Firebase 데이터베이스에 연결할 수 없습니다.")
