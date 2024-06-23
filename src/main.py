import re
import logging
from urllib.parse import urljoin

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from constants import BASE_DIR, MAIN_DOC_URL, EXPECTED_STATUS, MAIN_PEP_URL
from utils import get_response, find_tag
from configs import configure_argument_parser, configure_logging
from outputs import control_output
from exceptions import NotFoundAllVersions


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')

    response = get_response(session, whats_new_url)

    if response is None:
        return

    soup = BeautifulSoup(response.text, features='lxml')

    section = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})
    div = find_tag(section, 'div', attrs={'class': 'toctree-wrapper'})
    tag_li = div.find_all('li', attrs={'class': 'toctree-l1'})
    result = [('Ссылка на статью', 'Заголовок', 'Редактор, автор')]
    for sec in tqdm(tag_li):
        tag_a = urljoin(whats_new_url, sec.find('a')['href'])
        resp = get_response(session, tag_a)

        if resp is None:
            continue

        soups = BeautifulSoup(resp.text, features='lxml')
        h1 = find_tag(soups, 'h1')
        dl = find_tag(soups, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        result.append((tag_a, h1.text, dl_text))

    return result


def latest_versions(session):
    response = get_response(session, MAIN_DOC_URL)

    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    sidebar = find_tag(soup, 'div', attrs={'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')

    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise NotFoundAllVersions('Ничего не нашлось!')

    results = [('Ссылка на документацию', 'Версия', 'Статус')]
    for a_tag in a_tags:
        pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
        result = re.search(pattern, a_tag.text)
        if result is not None:
            results.append((a_tag['href'], result.group(1), result.group(2)))
        else:
            results.append((a_tag['href'], a_tag.text, 'Nothing'))

    return results


def download(session):

    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')

    response = get_response(session, downloads_url)

    if response is None:
        return

    soup = BeautifulSoup(response.text, features='lxml')
    div = find_tag(soup, 'div', attrs={'role': 'main'})
    table = find_tag(div, 'table', attrs={'class': 'docutils'})
    pdf_4 = find_tag(table, 'a', attrs={'href': re.compile(r'.+pdf-a4\.zip$')})
    link = urljoin(downloads_url, pdf_4['href'])
    filename = link.split('/')[-1]
    download_dir = BASE_DIR / 'downloads'

    download_dir.mkdir(exist_ok=True)
    archive_path = download_dir / filename

    response = session.get(link)

    with open(archive_path, 'wb') as write_file:
        write_file.write(response.content)

    logging.info(f'Архив был загружен и сохранен: {archive_path}')


def pep(session):
    writes_in_file = [('Статус', 'Количетство')]
    total = 0
    count_pep = {
        'A': 0, 'D': 0, 'F': 0, 'P': 0,
        'R': 0, 'S': 0, 'W': 0, '': 0
    }
    response = get_response(session, MAIN_PEP_URL)

    soup = BeautifulSoup(response.text, features='lxml')

    pep_content = find_tag(soup, 'section', {'id': "index-by-category"})
    all_section_category = pep_content.find_all('section')
    for section in tqdm(all_section_category):
        tbody = find_tag(section, 'tbody')
        tr_result = tbody.find_all('tr')
        for tr in tr_result:
            total += 1
            href = find_tag(
                tr, 'a', {'class': "pep reference internal"})['href']
            status_on_card = find_tag(tr, 'abbr').text

            short_status_card = (
                status_on_card[-1] if len(status_on_card) == 2 else '')
            expected_status_on_card = EXPECTED_STATUS[short_status_card]
            link_page_pep = urljoin(MAIN_PEP_URL, href)
            response = get_response(session, link_page_pep)
            soup = BeautifulSoup(response.text, features='lxml')
            abbr = find_tag(soup, 'abbr').text
            status = abbr[0] if abbr != 'Draft' else ''
            status_on_site = EXPECTED_STATUS[status]
            if abbr in status_on_site:
                count_pep[status] += 1
            else:
                status = abbr
                status_on_site = status
            if short_status_card != status:
                if isinstance(expected_status_on_card, tuple):
                    if len(expected_status_on_card) == 1:
                        expected_status_on_card = expected_status_on_card[0]
                if len(status_on_site) == 1:
                    status_on_site = status_on_site[0]
                msg_discrepancy = (
                    'Несовпадающие статусы: ' +
                    f'URL -> {link_page_pep} , ' +
                    f'Статус в карточке -> {expected_status_on_card}, ' +
                    f'Статус на сайте -> {status_on_site}'
                )
                logging.info(msg_discrepancy)

    for pep in count_pep:
        if len(EXPECTED_STATUS[pep]) == 2:
            full_pep = ', '.join(EXPECTED_STATUS[pep])
        else:
            full_pep = EXPECTED_STATUS[pep][0]
        writes_in_file.append((full_pep, count_pep[pep]))
    writes_in_file.append(('Total', total))
    return writes_in_file


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')
    agrs_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    agrs = agrs_parser.parse_args()
    logging.info(f'Аргументы командной строки -> {agrs}')
    session = requests_cache.CachedSession()
    if agrs.clear_cache:
        session.cache.clear()
    parser_mode = agrs.mode
    results = MODE_TO_FUNCTION[parser_mode](session)
    if results is not None:
        control_output(results, agrs)
    logging.info('Парсер завершил работу')


if __name__ == '__main__':
    main()
