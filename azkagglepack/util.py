import sys
import psutil

import logging

import json
import os
import sys
from collections import deque

from time import time, strftime, gmtime
from . import constants as C

import torch.cuda as cutorch
import pymongo
import pandas as pd
import numpy as np
from .datasets import SaltDataset
import yaml

log = logging.getLogger(C.LOGGER)


def get_config(set_env=True):
    try:
        conf = yaml.load(open(C.CONFIG_FILE, "r"))
        if set_env:
            os.environ.update(conf)
        return conf
    except:
        log.warning("Unable to read config file. Ignoring")
        return {}


conf = get_config()


def get_conf_entry(entry_name, category=None):
    '''
    poll env first, then conf, then return error if not found
    '''
    if entry_name in os.environ:
        return os.environ[entry_name]
    elif category and entry_name in conf:
        return conf[category][entry_name]
    elif entry_name in conf and not category:
        return conf[entry_name]
    else:
        raise KeyError(f"{entry_name} is not present in neither config nor env")


class TicTocTimer:
    def __init__(self):
        self.reset()

    def reset(self):
        self.start_time = time()
        self.pid = os.getpid()
        self.process = psutil.Process(self.pid)
        self.start_mem = self.get_mem()
        self.timings = deque()
        self.cuda_available = cutorch.is_available()
        self.start_gpu_mem = self.get_gpu_mem() if self.cuda_available else 0
        log.debug("Global timer set {}".format(self.start_time))

    def get_mem(self):
        return self.process.memory_info().rss

    def get_gpu_mem(self):
        if cutorch.is_available():
            return sum([cutorch.memory_cached(i) for i in range(cutorch.device_count())])
        else:
            return 0

    def get_msg(self, msg):
        ret = "{}, global time: {:.2f}, mem use:{:.2f}GB".format(msg,
                                                                 time() - self.start_time,
                                                                 self.get_mem() / 2 ** 30)
        if self.cuda_available: ret += ", GPU_MEM: {:.2f}GB".format(self.get_gpu_mem() / 2 ** 30)

        return ret

    def get_diff_msg(self, msg, t, mem, gpu_mem=0):
        ret = msg + \
              " time:{:.2f} global_time:{:.2f} step_mem:{:.2f}MB mem_use:{:.2f}GB".format(time() - t,
                                                                                          time() - self.start_time,
                                                                                          (
                                                                                                      self.get_mem() - mem) / 2 ** 20,
                                                                                          self.get_mem() / 2 ** 30)
        if gpu_mem > 0:
            ret += " step_gpu:{:.2f}MB gpu_mem:{:.2f}GB".format((self.get_gpu_mem() - gpu_mem) / 2 ** 20,
                                                                self.get_gpu_mem() / 2 ** 30)

        return ret

    def tic(self, msg):
        self.timings.appendleft((msg, time(), self.get_mem(), self.get_gpu_mem()))
        log.info("Started:" + self.get_msg(msg))

    def toc(self, vals=None):
        msg, t, mem, gpu_mem = self.timings.popleft()
        if vals is not None:
            msg = msg.format(vals)
        log.info("Finished: " + self.get_diff_msg(msg, t, mem, gpu_mem))

    def get_global_time(self):
        return time() - self.start_time


timer = TicTocTimer()


def get_timer():
    return timer


def set_console_logger(log):
    log.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        # '%(name)s:[%(asctime)s] {%(module)s.%(funcName)s:%(lineno)d %(levelname)s} - %(message)s')
        '[%(asctime)s][%(levelname)s]: %(message)s', "%d.%m.%y %H:%M:%S")
    # '%m-%d %H:%M:%S'

    handl = logging.StreamHandler(stream=sys.stdout)
    handl.setFormatter(formatter)
    log.addHandler(handl)
    return formatter


class TelegramHelper(object):
    def __init__(self, token=None, chat=None):
        try:
            import telegram
        except Exception as e:
            log.error("Telegram failed with error message: {}".format(e))
            self._offline = True
        self._token = token if token else get_conf_entry("TELEGRAM_TOKEN")
        self._chat = chat if chat else get_conf_entry("TELEGRAM_CHAT")
        self._bot = telegram.Bot(token=self._token)

    def send_telegram(self, msg):
        try:
            self._bot.send_message(self._chat, text=msg)
        except Exception as e:
            log.error("Telegram failed with exception: {}".format(e))


def get_run_hist(run_id, fold="0"):
    cli = pymongo.MongoClient(host=get_config()["MONGO_URL"])
    db = cli.get_database("kaggle-salt")
    coll = db.get_collection("runs")
    run = list(coll.find({"_id": run_id}))[0]

    hist = run["info"]["skorch_history"]
    fold_hist = hist[fold]["py/seq"]
    return pd.DataFrame(fold_hist).drop("batches", axis=1)


def get_folds(folds_file, fold, preds_file):
    folds = pd.read_pickle(os.path.join(C.FOLDS_DIR, folds_file))
    val_img_list = folds[fold][1]

    val_preds = np.load(preds_file)

    return {"val_img_list": val_img_list, "val_preds": val_preds}


def get_masks(img_list):
    val_ds = SaltDataset(C.TRAIN_DIR, name_list=img_list,
                         transform_list=["gray", "totensor"])
    masks = np.array([i[1].numpy() for i in val_ds])
    masks = np.int32(masks.squeeze())
    return masks

