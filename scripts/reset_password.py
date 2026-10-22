"""Local administrator recovery; run inside the hub container using an interactive TTY."""
import getpass
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from auth import Accounts

def main():
    accounts=Accounts(os.environ.get('HUB_DATA_DIR','/data/tasks'));account=accounts.get()
    if not account:raise SystemExit('管理员尚未创建，请打开网页完成首次设置')
    print('重置管理员密码，所有旧登录将失效。任务、音乐与平台凭据保留。')
    password=getpass.getpass('新密码（10～128 位）：')
    if not 10<=len(password)<=128:raise SystemExit('密码长度须为 10～128 位')
    if password!=getpass.getpass('再次输入：'):raise SystemExit('两次输入不一致，未做修改')
    if not accounts.change(account[2],password):raise SystemExit('账号已更新，请重试')
    print('密码已更新，请通过网页登录。')

if __name__=='__main__':main()
