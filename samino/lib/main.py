# pip install -r requirements.txt
from datetime import datetime
from dataclasses import dataclass
from threading import Thread
from colorama import Fore
from k_amino import (
    SubClient,
    Client,
    lib
)
import logging
import ujson
import pytz
import time

# editable.
FILE = "new-accounts.json"
COMMUNITY = "http://aminoapps.com/c/Heaven_999"
DEBUG = False

# runtime vars
LOGGERS = {}
START_INIT_COLDOWN = 5
PROCESS_COLDOWN = 10
ERROR_COLDOWN = 10
SEND_ACTIVITY_TIMES = 24
SEND_ACTIVITY_SLEEP = 16
MANY_REQUESTS_COLDOWN = 30


class Formatter(logging.Formatter):
    _format = '%s</> {levelname}: %s{name}%s - %s{message}'
    colors = {
        logging.DEBUG: (Fore.LIGHTMAGENTA_EX, Fore.LIGHTBLACK_EX, Fore.LIGHTMAGENTA_EX, Fore.RESET),
        logging.INFO: (Fore.LIGHTMAGENTA_EX, Fore.LIGHTCYAN_EX, Fore.LIGHTMAGENTA_EX, Fore.RESET),
        logging.WARNING: (Fore.LIGHTMAGENTA_EX, Fore.LIGHTYELLOW_EX, Fore.LIGHTMAGENTA_EX, Fore.RESET),
        logging.ERROR: (Fore.LIGHTMAGENTA_EX, Fore.LIGHTRED_EX, Fore.LIGHTMAGENTA_EX, Fore.RESET),
        logging.CRITICAL: (Fore.LIGHTMAGENTA_EX, Fore.RED, Fore.LIGHTMAGENTA_EX, Fore.RESET),
    }

    def format(self, record: logging.LogRecord) -> str:
        fmt = self._format % self.colors[record.levelno]
        return logging.Formatter(fmt, style='{').format(record)


@dataclass
class Account:
    email: str
    password: str
    device: str
    proxy: str

    authenticated = 0.0
    community = 0
    invitation = None
    cm_joined = False
    coins = 0

    def __hash__(self) -> int:
        return hash(self.email)


def getLogger(email: str) -> logging.Logger:
    if email in LOGGERS:
        return LOGGERS[email]
    logger = logging.getLogger(email)
    hd = logging.StreamHandler()
    level = logging.DEBUG if DEBUG else logging.INFO
    logger.setLevel(level)
    hd.setLevel(level)
    hd.setFormatter(Formatter())
    logger.addHandler(hd)
    LOGGERS[email] = logger
    return logger


def setup(account: Account, amino: Client) -> None:
    logger = getLogger(account.email)
    while True:
        try:
            info = amino.get_from_link(COMMUNITY)
        except lib.TooManyRequests:
            logger.warning('setup: too many requests. slepping %ds.' %
                           MANY_REQUESTS_COLDOWN)
            time.sleep(MANY_REQUESTS_COLDOWN)
            continue
        except lib.AminoBaseException as exc:
            logger.error('setup: %s', exc.args[0].get('api:message'))
            time.sleep(ERROR_COLDOWN)
            continue
        else:
            account.community = info.comId
            account.invitation = info.json.get('invitationId')
            logger.debug(
                f'community: {account.community}, invitation: {account.invitation}')
            logger.info('starting...')
            break


def login(account: Account, amino: Client) -> None:
    logger = getLogger(account.email)
    while not amino.sid:
        try:
            user = amino.login(account.email, account.password)
        except lib.TooManyRequests:
            logger.warning('too many requests. slepping %ds.' %
                           MANY_REQUESTS_COLDOWN)
            time.sleep(MANY_REQUESTS_COLDOWN)
            continue
        except lib.AminoBaseException as exc:
            logger.error(str(exc.args[0]))
            time.sleep(ERROR_COLDOWN)
            continue
        else:
            logger.info('authenticated.')
            break


def join_community(account: Account, amino: Client) -> None:
    logger = getLogger(account.email)
    while True:
        try:
            amino.join_community(account.community, account.invitation)
        except lib.TooManyRequests:
            logger.warning('too many requests. slepping %ds.' %
                           MANY_REQUESTS_COLDOWN)
            time.sleep(MANY_REQUESTS_COLDOWN)
            continue
        except lib.AminoBaseException as exc:
            logger.error(str(exc.args[0]))
            time.sleep(ERROR_COLDOWN)
            continue
        else:
            logger.info('community joined.')
            account.cm_joined = True
            break


def send_active_time(account: Account, subclient: SubClient) -> None:
    logger = getLogger(account.email)
    for t in range(SEND_ACTIVITY_TIMES):
        while True:
            try:
                subclient.send_active_time(
                    tzFilter(), timers=lib.active_time(hours=4))
            except lib.TooManyRequests:
                logger.warning('too many requests. slepping %ds.' %
                               MANY_REQUESTS_COLDOWN)
                time.sleep(MANY_REQUESTS_COLDOWN)
                continue
            except lib.AminoBaseException as exc:
                logger.error(str(exc.args[0]))
                time.sleep(ERROR_COLDOWN)
                continue
            else:
                logger.info('send activity %d times.', t + 1)
                time.sleep(SEND_ACTIVITY_SLEEP)
                break


def wait_coins(account: Account) -> None:
    logger = getLogger(account.email)
    dt = datetime.now()
    current = dt.hour * 60 * 60 + dt.minute * 60
    final = (dt.hour + 1) * 60 * 60 + 15 * 60
    logger.info('waitting to %d:%d', dt.hour + 1, 15)
    time.sleep(final - current)

#dict format is {"http": "proxy-here", "https": "proxy-here"}

def threadit(account: Account) -> None:
    proxy = account.proxy
    amino = Client(account.device, proxy if isinstance(
        proxy, dict) else {"http://": proxy, "https://": proxy})
    setup(account, amino)
    while True:
        if time.time() - account.authenticated > 60 * 60 * 12:
            login(account, amino)
            time.sleep(PROCESS_COLDOWN)
        if not account.cm_joined:
            join_community(account, amino)
            time.sleep(PROCESS_COLDOWN)
        subclient = SubClient(account.community, amino.proxies)
        send_active_time(account, subclient)
        time.sleep(PROCESS_COLDOWN)
        wait_coins(account)


def tzFilter(hour: int = 23) -> int:
    zones = ('Etc/GMT' + (f'+{i}' if i > 0 else str(i))
             for i in range(-12, 12))
    for zone in zones:
        zone = datetime.now(pytz.timezone(zone))
        if int(zone.strftime('%H')) != hour:
            continue
        return int(zone.strftime('%Z').replace('GMT', '00')) * 60


def main():
    try:
        with open(FILE, 'r') as f:
            data = ujson.load(f)
        accounts = {Account(a['email'], a['password'],
                            a['device'], a['proxy']) for a in data}
        threads = [Thread(target=threadit, args=[a], daemon=True)
                   for a in accounts]
        for thread in threads:
            thread.start()
            time.sleep(START_INIT_COLDOWN)
        while True:
            #    # keep alive task
            time.sleep(60)
    except KeyboardInterrupt:
        return


if __name__ == '__main__':
    main()
