import logging

from requests import RequestException

from exceptions import ParserFindTagException


def get_response(session, url):
    try:
        resposne = session.get(url)
        resposne.encoding = 'utf-8'
        return resposne
    except RequestException:
        logging.exception(
            'fВозникла ошибка при загрузке страницы {url}',
            exc_info=True
        )


def find_tag(soup, tag, attrs=None):
    searched_teg = soup.find(tag, attrs=(attrs or {}))
    if searched_teg is None:
        error_msg = f'Не найден тег {tag} {attrs}'
        logging.error(error_msg, stack_info=True)
        raise ParserFindTagException(error_msg)
    return searched_teg
