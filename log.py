import logging

class Logger:
    setting = {'level':logging.DEBUG, 'filename':'debug_log', 'filemode':'w'}    

    @classmethod
    def get_logger(cls, name):
        logger = logging.getLogger(name)

    @classmethod
    def set_output_name(cls, name):
        setting['filename'] = name
        logging.basicConfig(**cls.setting)

    @classmethod
    def set_level(cls, level):
        setting['level'] = level
        logging.basicConfig(**cls.setting)

