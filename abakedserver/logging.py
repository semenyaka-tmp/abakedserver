import logging
import logging.handlers
import sys

def configure_logger(name: str) -> logging.Logger:
    """
    Configure a logger with rotating file and console handlers.
    
    Args:
        name (str): Logger name, typically package prefix (e.g., 'abakedserver').
    
    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        file_handler = logging.handlers.RotatingFileHandler(
            'abakedserver.log', maxBytes=10*1024*1024, backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger

