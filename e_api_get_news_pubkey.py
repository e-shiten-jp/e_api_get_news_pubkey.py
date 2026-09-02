# -*- coding: utf-8 -*-
# Copyright (c) 2021 Tachibana Securities Co., Ltd. All rights reserved.

# 2021.07.09,   yo.
# 2023.04.14 reviced,   yo.
# 2025.07.27 reviced,   yo.
# 2026.08.14 reviced,   yo.
# 2026.08.28 reviced,   yo.
#
# 立花証券ｅ支店ＡＰＩ利用のサンプルコード
#
# 動作確認
# Python 3.13.5 / debian13
# API v4r10
#
# ------------------------------------------------------------------
#
# APIの基本設計について
# 
# 本APIは、プログラミング初心者や非ITエンジニアの方にも
# 利用しやすいよう、URLにJSON形式のパラメーターを付加して
# 送信する独自方式を採用しています。
# 
# 一般的なWeb APIとは異なる構成ですが、
# HTTPヘッダーやPOSTデータなどの知識を最小限に
# 抑えながら利用できることを重視しています。
# 
# このため、本APIは、URLとJSON文字列を組み立てて
# 送信するだけで利用でき、特別な知識を必要とせず、
# 各種スクリプト言語からも実装しやすいことを
# 優先した設計となっています。
#  
# ------------------------------------------------------------------
# 
# 固定IP指定の推奨
# 
# 秘密鍵、第2パスワードファイル、またはログインレスポンスファイルが
# 万が一流出した場合、第三者に不正ログインされるリスクがあります。
# 
# 安全のため、接続元を固定IPに限定する設定（IP制限）を
# 行っての利用を強く推奨いたします。
# 
# ------------------------------------------------------------------
#
# 利用方法: 
# 事前に「e_api_login_pubkey.py」を実行して、仮想URL等を取得しておいてください。
# 実行は「e_api_login_pubkey.py」と同じディレクトリで行ってください。
#
# ファイル構成：
# ~/e_api/                        ← API実行基盤（権限: 700 / 所有者のみアクセス可）
# ├── .auth/                      ← 鍵・暗号化データ格納（権限: 700）
# │   ├── file_pwd2.txt           ← 第2パスワード保存ファイル（手動作成。注文・訂正・取消以外は不要）
# │   └── file_login_response.txt ← ログイン応答出力先（自動生成）
# ├── file_url_info.txt           ← API接続情報ファイル（手動作成）
# ├── e_api_login_pubkey.py
# │
# └── [本実行プログラム]
# 
# 
# ~/e_api/file_url_info.txtの内容例：
# {
#     "sUrl": "https://demo-kabuka.e-shiten.jp/e_api_v4r10/",
#     "sJsonOfmt": "5"
# }
# 
#
# == ご注意: ========================================
#   本番環境にに接続した場合、実際に市場に注文が出ます。
#   市場で約定した場合取り消せません。
# ==================================================
#
# 取得可能なニュース情報の範囲
#   過去９０日（例：当日営業日が 20260814 の場合 20260516 まで取得可能）
#
# ニュースデータ取得サイクル
#   過去情報は毎朝 AM 05:40 ～ 05:50 に情報発信元から１度だけ情報取得します。
#   当日情報は AM 06:00 ～ 23:59 まで毎分１回、情報発信元から情報を取得します。
# 
# 該当情報取得時間帯（本機能要求送信等）は上記を考慮しご利用願います。
#

import urllib3
import datetime
import json
import os
import urllib.parse
from zoneinfo import ZoneInfo
import base64           # ニュース取得用
import csv              # csv.writerモジュールを使う。p_TXに改行が含まれるため。


# コマンド用パラメーター -------------------    

# 取得する日付を設定してください。
P_DT = 'YYYYMMDD'                   # ニュース日付（YYYYMMDD）
# P_DT = '20260902'                   # ニュース日付（YYYYMMDD）

# 出力ファイル名の設定
# 書き込むファイル名。カレントディレクトリに上書きモードでファイルが作成される。
FNAME_OUTPUT = 'news_' + P_DT +'.csv'

# --- 共通設定項目 ------------------------------------------------------------
FNAME_URL_INFO = "file_url_info.txt"                # API接続情報ファイル
FNAME_PASSWD2 = "./.auth/file_pwd2.txt"              # 第二パスワード保存ファイル
FNAME_LOGIN_RESPONSE = "./.auth/file_login_response.txt"  # ログイン応答保存先
FNAME_INFO_P_NO = "file_info_p_no.txt"              # p_no保存ファイル

# --- 通信堅牢化のための設定項目 ---
API_TIMEOUT_SECONDS = 15.0  # タイムアウト時間（秒）: 応答がない場合15秒で切り上げる
MAX_RETRY_COUNT = 3         # 最大リトライ回数: 通信エラー時に自動再試行する回数
RETRY_INTERVAL_SECONDS = 5  # リトライ間隔（秒）: 再試行する前に待機する時間
# --- 以上設定項目 -------------------------------------------------------------------------




# --- 共通ユーティリティ関数 ----------------------------------------------

def func_p_sd_date():
    """
    機能: システム時刻を"p_sd_date"の書式の文字列で返す。
    返値: "p_sd_date"の書式の文字列。 API規定書式 "YYYY.MM.DD-hh:mm:ss.sss"
    引数1: なし
    備考: 
        日本標準時（Japan Standard Time、JST）を利用のこと。
    """
    dt_now = datetime.datetime.now(
        # 日本標準時（Japan Standard Time、JST）を利用
        ZoneInfo("Asia/Tokyo")
    )
    # 年.月.日-時:分:秒 の部分を作成
    str_date = dt_now.strftime("%Y.%m.%d-%H:%M:%S")
    
    # マイクロ秒（6桁ゼロ埋め）から先頭の3桁を切り出してミリ秒を作成
    str_micro = f"{dt_now.microsecond:06d}"
    str_ms = str_micro[0:3]
    
    # ドットで結合してAPI規定書式を完成
    return str_date + "." + str_ms


def func_replace_urlencode(str_input):
    """
    URLエンコードを行う。

    URLでは、スペースや「&」「+」「?」などの記号が
    特別な意味を持つため、そのまま送信できない場合がある。
    そのため、これらの文字を「%xx」形式へ変換する。

    例:
        "A B+C" → "A%20B%2BC"

    本サンプルでは Python標準ライブラリの
    urllib.parse.quote() を利用してURLエンコードを行う。

    他言語へ移植する場合も、自前で変換処理を作成するのではなく、
    各言語が提供する標準のURLエンコード関数を利用することを推奨する。

    主な対応例:
        Python      : urllib.parse.quote()
        Java        : java.net.URLEncoder.encode()
        C#          : Uri.EscapeDataString()
        JavaScript  : encodeURIComponent()
        Go          : url.QueryEscape()

    Parameters
    ----------
    str_input : str
        URLエンコード対象文字列

    Returns
    -------
    str
        URLエンコード後の文字列
    """
    return urllib.parse.quote(str_input, safe='')


def func_read_from_file(str_fname):
    """ファイルから文字情報を一括読み込み（BOMを排除）"""
    str_read = ''
    try:
        # utf-8-sig を指定してBOMを自動的に排除しファイルを開く
        with open(str_fname, 'r', encoding='utf-8-sig') as fin:
            while True:
                line = fin.readline()
                if not line:
                    break
                str_read = str_read + line
        return str_read
    except IOError as e:
        print(f"[エラー] ファイルを読み込めません: {str_fname}")
        raise e


def func_write_to_file(str_fname_output, str_data):
    """ファイルに書き込み、権限を所有者のみ(600)に制限"""
    try:
        # 出力先フォルダの存在を確認し、存在しない場合は自動作成
        str_dir = os.path.dirname(str_fname_output)
        if str_dir and not os.path.exists(str_dir):
            os.makedirs(str_dir, exist_ok=True)

        # データをファイルへ書き込み
        with open(str_fname_output, 'w', encoding='utf-8') as fout:
            fout.write(str_data)
        
        # パーミッションを600（所有者のみ読み書き可能）に制限
        os.chmod(str_fname_output, 0o600)
    except IOError as e:
        print(f"[エラー] ファイルに書き込めません: {str_fname_output}")
        raise e


def func_get_url_info(fname):
    """
    file_url_info.txt からAPI接続設定を取得

    機能: API接続情報をファイルから取得し辞書型で返す
    引数1: 接続先情報を保存したファイル名: fname_url_info

    サポートへの問い合わせは、sJsonOfmt:'5'でお願いします。
    """
    str_url_info = func_read_from_file(fname)
    # JSON形式の文字列を辞書型で取り出す
    return  json.loads(str_url_info)    


def func_get_login_response(str_fname):
    '''
    ログインレスポンスを取得
    '''
    str_login_response = func_read_from_file(str_fname)
    dic_login_response = json.loads(str_login_response)
    return dic_login_response
    

def func_get_p_no(fname):
    """ 
    機能: p_noをファイルから取得する
    引数1: p_noを保存したファイル名（fname_info_p_no = "e_api_info_p_no.txt"）
    """
    str_p_no_info = func_read_from_file(fname)
    # JSON形式の文字列を辞書型で取り出す
    json_p_no_info = json.loads(str_p_no_info)
    int_p_no = int(json_p_no_info.get('p_no'))
    return int_p_no


def func_save_p_no(str_fname_output, int_p_no):
    """p_noを保存するためのJSONファイルを生成"""
    p_no_dict = {"p_no": str(int_p_no)}
    json_data = json.dumps(p_no_dict, indent=4)
    func_write_to_file(str_fname_output, json_data)
    print(f'現在の "p_no" を保存しました。 p_no = {int_p_no} -> {str_fname_output}')


def func_make_url_request_from_dic(
                                    auth_flg,       # ログインFlag。    login:true   login以外:false
                                    url_target,     # 接続先URL
                                    work_dic_req    # API要求項目
):
    '''
    API問合せ用完全URL（クエリパラメータ付）を作成
    
    ------------------------------------------------------------------

    APIの基本設計について

    本APIは、プログラミング初心者や非ITエンジニアの方にも
    利用しやすいよう、URLにJSON形式のパラメーターを付加して
    送信する独自方式を採用しています。

    一般的なWeb APIとは異なる構成ですが、
    HTTPヘッダーやPOSTデータなどの知識を最小限に
    抑えながら利用できることを重視しています。

    このため、本APIは、URLとJSON文字列を組み立てて
    送信するだけで利用でき、特別な知識を必要とせず、
    各種スクリプト言語からも実装しやすいことを
    優先した設計となっています。
    
    ------------------------------------------------------------------
    JSONをHTTPボディではなくURLに付加して送信します。
    詳細はAPIマニュアル参照。
    備考：
        サポートへの問い合わせを考慮し、項目ごとの改行とタブを入れてあります。
    '''
    str_url = url_target
    if auth_flg:
        str_url = urllib.parse.urljoin(str_url, 'auth/')
    json_param = json.dumps(work_dic_req, indent=4, ensure_ascii=False)
    return f"{str_url}?{json_param}"


def func_api_req(str_request_method, str_url): 
    """
    APIリクエストの送信と、Shift-JIS応答のデコード（リトライ・タイムアウト対応版）
    """
    # HTTP通信ライブラリ urllib3 を利用します。
    #
    # requests ライブラリでも同様の処理は可能ですが、
    # 本サンプルでは APIサーバーへの接続処理が分かりやすいよう、
    # より基本的な urllib3 を利用しています。
    #
    # 他言語へ移植する場合も、
    # 「HTTPクライアント生成 → リクエスト送信 → レスポンス受信」
    # の流れを対応するライブラリへ置き換えてください。

    # 接続および読み込みのタイムアウト時間を設定
    timeout_config = urllib3.Timeout(connect=API_TIMEOUT_SECONDS, read=API_TIMEOUT_SECONDS)
    http = urllib3.PoolManager()
    
    response_data = None
    status_code = None

    # 最大試行回数に達するまで通信をリトライ
    for attempt in range(1, MAX_RETRY_COUNT + 1):
        try:
            # 2回目以降の試行（再接続）の前に、指定されたインターバル時間待機
            if attempt > 1:
                print(f"[{attempt}/{MAX_RETRY_COUNT} 回目] 再接続を試みます...（{RETRY_INTERVAL_SECONDS}秒待機）")
                time.sleep(RETRY_INTERVAL_SECONDS)

            req = http.request(str_request_method, str_url, timeout=timeout_config)
            status_code = req.status
            response_data = req.data
            break  # 正常に通信できた場合はループを抜ける

        except (TimeoutError, MaxRetryError) as ce:
            print(f"\n[警告] 通信エラーが発生しました (試行: {attempt}/{MAX_RETRY_COUNT})")
            print(f"エラー詳細: {ce}")
            
            # 最大リトライ回数を超えて失敗した場合はConnectionErrorを発生
            if attempt == MAX_RETRY_COUNT:
                raise ConnectionError(
                    f"APIサーバーへの接続に規定回数失敗しました。サーバーがメンテナンス中か、停止している可能性があります。\n"
                    f"設定されたタイムアウト時間: {API_TIMEOUT_SECONDS}秒"
                )
        except Exception as ex:
            print(f"\n[警告] 予期せぬネットワーク例外が発生しました: {ex}")
            if attempt == MAX_RETRY_COUNT:
                raise ex

    print(f"HTTP Status: {status_code}")

    # 受信した電文をShift-JISからUTF-8へデコード（不正なバイトは無視）
    str_response = response_data.decode("shift-jis", errors="ignore")
    return str_response


def func_print_sendding_url(str_sending_url):
    print('--- 送信電文 -------------------------------------------')
    print(str_sending_url)


def func_print_response(str_output, long_limit):
    print('--- 受信電文 -------------------------------------------')
    print(str_output[:long_limit])
    if len(str_output) < long_limit:
        print('--- 以上 受信電文 --------------------------------------')
    else:
        print('--- ', long_limit, '文字以降省略 -----------------------')



def func_api_request_from_dic(
                                flg_login,          # ログインFlag。    login:true   login以外:false
                                destination_url,    # 接続先URL。
                                                    #   ログイン時は、FNAME_URL_INFOから取得する接続先。
                                                    #   それ以外はログインレスポンスで指定される仮想URL。
                                dic_req_item        # API要求項目
                            ):
    '''
    APIへの問い合わせを実行する。
    '''
    # URL文字列の作成
    str_url = func_make_url_request_from_dic(
                                                flg_login,          # ログインFlag。    login:true   login以外:false
                                                destination_url,    # 接続先URL
                                                dic_req_item        # API要求項目
    )

    # 送信電文の出力
    func_print_sendding_url(str_url)

    # APIへの問い合わせ。
    # リクエストメソッドの指定('GET'、'POST'どちらでも動作します。)
    str_api_response = func_api_req('POST', str_url)

    # 受信電文の出力（最大文字数指定: 3,000）
    func_print_response(str_api_response, 3*10**3)

    # apiの返り値（JSON形式の文字列）を辞書型で取り出す
    dic_api_response = json.loads(str_api_response)
    
    return dic_api_response

# --- 共通ユーティリティ関数 ----------------------------------------------



# 機能: 14.ニュース問合取得の日本語項目名を取得
# 引数: 列名
# 返値: 漢字名 string型
def func_column_kanji_CLMMfdsGetNews(str_column_name):
    if str_column_name == 'p_ID' : str_name_kanji = 'ニュースＩＤ'     # 情報（レコード）識別用ユニーク値
    elif str_column_name == 'p_TM' : str_name_kanji = 'ニュース時刻'     # HHMM
    elif str_column_name == 'p_CGL' : str_name_kanji = 'ニュースカテゴリリスト'     # 複数設定時は「|」区切り
                                                                                    # 【注意１】参照
    elif str_column_name == 'p_GNL' : str_name_kanji = 'ニュースジャンルリスト'     # 複数設定時は「|」区切り
                                                                                    # 【注意１】参照
    elif str_column_name == 'p_ISL' : str_name_kanji = 'ニュース関連銘柄コードリスト'       # 複数設定時は「|」区切り
    elif str_column_name == 'p_HDL' : str_name_kanji = 'ニュースヘッドライン（タイトル）'   # ShiftJIS 日本語コード文字列を BASE64 変換し設定
                                                                                            # 取得側で各デコード後利用する
    elif str_column_name == 'p_TX' : str_name_kanji = 'ニュースボディー（本文）'    # ShiftJIS 日本語コード文字列を BASE64 変換し設定
                                                                                    # 取得側で各デコード後利用する
    else :
        str_name_kanji = str_column_name
    return str_name_kanji



# 機能: ニュースヘッドライン（タイトル）、ニュースボディー（本文）をデコードする。
# 引数1: テキスト。string型。
# 備考:
# p_HDL、p_TXは、
# 元の文字列はcp932で、それをパーセントエンコード(URLエンコード)して、base64変換されている。
# 元の文字列に戻すためには、base64でデコードしてから、パーセントエンコードのデコードを行う。
#
# base64のデコード（base64.b64decode）は、引数の文字列をバイト型にしてから実行する。
# パーセントエンコード(URLエンコード)のデコード（urllib.parse.unquote）は、string型にしてから実行する。
# 
# デコードは、次の手順で行なう。
# string型で取得 →
#   byte型に変換 →
#       base64デコード: base64.b64decode() →
#           string型に変換 →
#               パーセントエンコードのデコード: urllib.parse.unquote()
def func_decode_base64_data(str_encoded_text):
    byte_base64_text = str_encoded_text.encode()        # string型のp_HDLをbyte型に変換
    byte_escape_text = base64.b64decode(byte_base64_text)  # base64でデコード。デコードされた文字列は、元のパーセントエンコード(URLエンコード)された文字列。
    str_escape_text = byte_escape_text.decode()         # urllib.parse.unquoteは引数がstring型。
    str_text = urllib.parse.unquote(
                                        str_escape_text, 
                                        encoding='cp932')   # urllib.parse.unquote の第1引数は、string型。
    return str_text



# 機能: csv形式でファイルに書き込む
# 返値: 
# 引数1:
# 引数2:
# 備考: 1行目は、タイトル行
#     2行目以降は、データ行 
def func_write_news(str_sTargetCLMID, \
                    json_return, \
                    str_master_filename
                    ):

    
    str_a_clmid = 'aCLMMfdsNews'
    print('取得データ：', str_sTargetCLMID)

    # 返り値からsTargetCLMID内のデータレコードのみ抜き出す
    list_return = json_return.get(str_a_clmid)
    
    if not list_return is None:
        try:
            # Linux標準の 'utf-8' (BOMなし) を指定
            # newline='' を指定することで、Pythonのcsvモジュールが環境に合わせた正しい改行を出力します
            with open(str_master_filename, "w", newline="", encoding="utf-8") as fout:

                # lineterminator='\n' を明示して、Linux標準の改行コード(LF)に統一します
                # quoting=csv.QUOTE_MINIMAL で、改行を含むセルを自動で「""」で囲みます
                writer = csv.writer(
                    fout, quoting=csv.QUOTE_MINIMAL, lineterminator="\n"
                )

                int_num_of_articles = len(list_return[0].keys())
                iter_keys = iter(list_return[0].keys())

                print("ファイル名:", str_master_filename)
                print("データ件数:", len(list_return))

                # --- タイトル行の作成 ---
                header_keys = []
                header_kanji = []

                for i in range(int_num_of_articles):
                    work_key = next(iter_keys)
                    work_kanji = func_column_kanji_CLMMfdsGetNews(work_key)

                    header_keys.append(work_key)
                    header_kanji.append(work_kanji)

                writer.writerow(header_keys)
                writer.writerow(header_kanji)

                # --- データ行の作成と書き込み ---
                for i in range(len(list_return)):

                    row_data = [
                        list_return[i]["p_ID"],
                        list_return[i]["p_TM"],
                        list_return[i]["p_CGL"],
                        list_return[i]["p_GNL"],
                        list_return[i]["p_ISL"],
                        func_decode_base64_data(list_return[i]["p_HDL"]),   #  base64デコード + パーセントエンコードのデコード
                        func_decode_base64_data(list_return[i]["p_TX"]),    # ←改行を含むデータ。  base64デコード + パーセントエンコードのデコード
                    ]

                    writer.writerow(row_data)

        except IOError as e:
            print("File can not write!!!")
            print(type(e))

    else :
        print('データ件数：0  （返されたデータはありませんでした。）')
        


# ======================================================================================================
#      プログラム始点 
# ======================================================================================================

if __name__ == "__main__":
    
    # 表示形式を接続情報ファイルから読み込む。
    dic_url_info = func_get_url_info(FNAME_URL_INFO)
    str_sJsonOfmt = dic_url_info.get("sJsonOfmt")

    # ログイン応答を保存した「file_login_response.txt」から、仮想URLと口座情報を取得
    dic_login_property = func_get_login_response(FNAME_LOGIN_RESPONSE)

    # 現在（前回利用した）のp_noをファイルから取得する
    my_p_no = func_get_p_no(FNAME_INFO_P_NO)
    my_p_no = my_p_no + 1
    # 更新した"p_no"を保存する。
    func_save_p_no(FNAME_INFO_P_NO, my_p_no)

    print()
    print('-- ニュース取得（日別） -------------------------------------------------------------')
    str_clmid = 'CLMMfdsGetNews'          # 14.ニュース問合取得

    # API要求項目のセット
    dic_req_item = {
        'p_no':             str(my_p_no),
        'p_sd_date':        func_p_sd_date(),

        'sCLMID':           str_clmid,                  # 14.ニュース問合取得
        'p_DT':             P_DT,                       # 日付	ニュース日付（YYYYMMDD）
        'sJsonOfmt':        str_sJsonOfmt               # 表示形式（サポートへの問い合わせでは'5'を指定指定した送信電文と受信電文で。）
    }

    # 'CLMMfdsGetMasterData'は、仮想URL:'sUrlMaster'
    str_connection_url = dic_login_property.get('sUrlMaster')

    # API問い合わせ実行
    dic_return = func_api_request_from_dic(
                                                False,                  # ログインFlag。    login:true   login以外:false
                                                str_connection_url,     # 接続先URL。
                                                                        #   ログイン時は、FNAME_URL_INFOから取得する接続先。
                                                                        #   それ以外はログインレスポンスで指定される仮想URL。
                                                dic_req_item            # API要求項目
                                            )

    if dic_return is not None:
        if dic_return.get('p_errno') != '-2' and dic_return.get('p_errno') != '2':
            # csv形式でファイルへの書き出し
            func_write_news(
                                        str_clmid, 
                                        dic_return, 
                                        FNAME_OUTPUT
                                    )

        elif dic_return.get('p_errno') == '-2' :
            print()
            print('p_errno', dic_return.get('p_errno'))
            print('p_err', dic_return.get('p_err'))
            print("パラメーターの設定に誤りが有ります。")

        # 仮想URLが無効になっている場合
        # if dic_return.get('p_errno') == '2':
        else:
            print()
            print('p_errno', dic_return.get('p_errno'))
            print('p_err', dic_return.get('p_err'))
            print("仮想URLが有効ではありません。")
            print("e_api_login_pubkey.py")
            print("の実行を再度行い、新しく仮想URL（1日券）を取得してください。")
    else:
        print('API接続自体の失敗')
        print('JSON形式の受信電文ではありません。接続先も含めて送信電文、受信電文を確認してください。')



    print()    
    print()
    # 最終の'p_no'を保存する。
    func_save_p_no(FNAME_INFO_P_NO, my_p_no)
