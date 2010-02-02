import web, re, urllib
from lxml.etree import parse, tostring, XML, XMLSyntaxError
from infogami.utils import delegate
from infogami import config
from openlibrary.catalog.utils import flip_name
from infogami.utils import view, template
import simplejson as json
from pprint import pformat
from openlibrary.plugins.upstream.utils import get_coverstore_url, render_template
from openlibrary.plugins.search.code import search as _edition_search
from infogami.plugins.api.code import jsonapi

class edition_search(_edition_search):
    path = "/search/edition"

solr_host = config.plugin_worksearch.get('solr')
solr_select_url = "http://" + solr_host + "/solr/works/select"

solr_subject_host = config.plugin_worksearch.get('subject_solr')
solr_subject_select_url = "http://" + solr_subject_host + "/solr/subjects/select"

to_drop = set('''!*"'();:@&=+$,/?%#[]''')

def str_to_key(s):
    return ''.join(c for c in s.lower() if c not in to_drop)

render = template.render

search_fields = ["key", "redirects", "title", "subtitle", "alternative_title", "alternative_subtitle", "edition_key", "by_statement", "publish_date", "lccn", "ia", "oclc", "isbn", "contributor", "publish_place", "publisher", "first_sentence", "author_key", "author_name", "author_alternative_name", "subject", "person", "place", "time"]

all_fields = search_fields + ["has_fulltext", "title_suggest", "edition_count", "publish_year", "language", "number_of_pages", "ia_count", "publisher_facet", "author_facet", "fiction", "first_publish_year"] 

facet_fields = ["has_fulltext", "author_facet", "language", "first_publish_year", "publisher_facet", "fiction", "subject_facet", "person_facet", "place_facet", "time_facet"]

facet_list_fields = [i for i in facet_fields if i not in ("has_fulltext", "fiction")]

def get_language_name(code):
    l = web.ctx.site.get('/languages/' + code)
    return l.name if l else "'%s' unknown" % code

def read_facets(root):
    bool_map = dict(true='yes', false='no')
    e_facet_counts = root.find("lst[@name='facet_counts']")
    e_facet_fields = e_facet_counts.find("lst[@name='facet_fields']")
    facets = {}
    for e_lst in e_facet_fields:
        assert e_lst.tag == 'lst'
        name = e_lst.attrib['name']
        if name == 'author_facet':
            name = 'author_key'
        if name in ('fiction', 'has_fulltext'): # boolean facets
            true_count = e_lst.find("int[@name='true']").text
            false_count = e_lst.find("int[@name='false']").text
            facets[name] = [
                ('true', 'yes', true_count),
                ('false', 'no', false_count),
            ]
            continue
        facets[name] = []
        for e in e_lst:
            if e.text == '0':
                continue
            k = e.attrib['name']
            if name == 'author_key':
                k, display = eval(k)
            elif name == 'language':
                display = get_language_name(k)
            else:
                display = k
            facets[name].append((k, display, e.text))
    return facets

def url_quote(s):
    if not s:
        return ''
    return urllib.quote_plus(s.encode('utf-8'))

re_baron = re.compile(r'^([A-Z][a-z]+), (.+) \1 Baron$')
def tidy_name(s):
    if s is None:
        return '<em>name missing</em>'
    if s == 'Mao, Zedong':
        return 'Mao Zedong'
    m = re_baron.match(s)
    if m:
        return m.group(2) + ' ' + m.group(1)
    if ' Baron ' in s:
        s = s[:s.find(' Baron ')]
    elif s.endswith(' Sir'):
        s = s[:-4]
    return flip_name(s)

re_isbn = re.compile('^([0-9]{9}[0-9X]|[0-9]{13})$')

def read_isbn(s):
    s = s.replace('-', '')
    return s if re_isbn.match(s) else None

re_fields = re.compile('(' + '|'.join(all_fields) + r'):', re.L)
re_author_key = re.compile(r'(OL\d+A)')

def run_solr_query(param = {}, rows=100, page=1, sort=None):
    q_list = []
    if 'q' in param:
        q_param = param['q'].strip()
    else:
        q_param = None
    offset = rows * (page - 1)
    if q_param:
        if q_param == '*:*' or re_fields.match(q_param):
            q_list.append(q_param)
        else:
            isbn = read_isbn(q_param)
            if isbn:
                q_list.append('isbn:(%s)' % isbn)
            else:
                q_list.append('(' + ' OR '.join('%s:(%s)' % (f, q_param) for f in search_fields) + ')')
    else:
        if 'author' in param:
            v = param['author'].strip()
            m = re_author_key.search(v)
            if m: # FIXME: 'OL123A OR OL234A'
                q_list.append('author_key:(' + m.group(1) + ')')
            else:
                q_list.append('author_name:(' + v + ')')

        check_params = ['title', 'publisher', 'isbn', 'oclc', 'lccn', 'contribtor', 'subject', 'place', 'person', 'time']
        q_list += ['%s:(%s)' % (k, param[k]) for k in check_params if k in param]

    q = url_quote(' AND '.join(q_list))

    solr_select = solr_select_url + "?version=2.2&q.op=AND&q=%s&start=%d&rows=%d&fl=key,author_name,author_key,title,edition_count,ia,has_fulltext,first_publish_year,cover_edition_key&qt=standard&wt=standard" % (q, offset, rows)
    solr_select += "&facet=true&" + '&'.join("facet.field=" + f for f in facet_fields)

    k = 'has_fulltext'
    if k in param:
        v = param[k].lower()
        if v not in ('true', 'false'):
            del param[k]
        param[k] == v
        solr_select += '&fq=%s:%s' % (k, v)

    for k in facet_list_fields:
        if k == 'author_facet':
            k = 'author_key'
        if k not in param:
            continue
        v = param[k]
        solr_select += ''.join('&fq=%s:"%s"' % (k, url_quote(l)) for l in v if l)
    if sort:
        solr_select += "&sort=" + url_quote(sort)
    print solr_select
    reply = urllib.urlopen(solr_select).read()
    return (reply, solr_select, q_list)

re_pre = re.compile(r'<pre>(.*)</pre>', re.S)

def do_search(param, sort, page=1, rows=100):
    (reply, solr_select, q_list) = run_solr_query(param, rows, page, sort)
    is_bad = False
    if reply.startswith('<html'):
        is_bad = True
    if not is_bad:
        try:
            root = XML(reply)
        except XMLSyntaxError:
            is_bad = True
    if is_bad:
        m = re_pre.search(reply)
        return web.storage(
            facet_counts = None,
            docs = [],
            is_advanced = bool(param.get('q', 'None')),
            num_found = None,
            solr_select = solr_select,
            q_list = q_list,
            error = (web.htmlunquote(m.group(1)) if m else reply),
        )

    docs = root.find('result')
    return web.storage(
        facet_counts = read_facets(root),
        docs = docs,
        is_advanced = bool(param.get('q', 'None')),
        num_found = (int(docs.attrib['numFound']) if docs is not None else None),
        solr_select = solr_select,
        q_list = q_list,
        error = None,
    )

def get_doc(doc):
    e_ia = doc.find("arr[@name='ia']")
    first_pub = None
    e_first_pub = doc.find("arr[@name='first_publish_year']")
    if e_first_pub is not None and len(e_first_pub) == 1:
        first_pub = e_first_pub[0].text

    ak = [e.text for e in doc.find("arr[@name='author_key']")]
    an = [e.text for e in doc.find("arr[@name='author_name']")]
    cover = doc.find("str[@name='cover_edition_key']")
    if cover is not None:
        print cover.text

    return web.storage(
        key = doc.find("str[@name='key']").text,
        title = doc.find("str[@name='title']").text,
        edition_count = int(doc.find("int[@name='edition_count']").text),
        ia = [e.text for e in (e_ia if e_ia is not None else [])],
        authors = [(i, tidy_name(j)) for i, j in zip(ak, an)],
        first_publish_year = first_pub,
        cover_edition_key = (cover.text if cover is not None else None),
    )

re_subject_types = re.compile('^(places|times|people)/(.*)')
subject_types = {
    'places': 'place',
    'times': 'time',
    'people': 'person',
    'subjects': 'subject',
}

def read_subject(path_info):
    m = re_subject_types.match(path_info)
    if m:
        subject_type = subject_types[m.group(1)]
        key = str_to_key(m.group(2)).lower().replace('_', ' ')
        full_key = '/subjects/%s/%s' % (m.group(1), key)
        q = '%s_key:"%s"' % (subject_type, url_quote(key))
    else:
        subject_type = 'subject'
        key = str_to_key(path_info).lower().replace('_', ' ')
        full_key = '/subjects/' + key
        q = 'subject_key:"%s"' % url_quote(key)
    return (subject_type, key, full_key, q)

@jsonapi
def subjects_covers(path_info):
    i = web.input(offset=0, limit=12)
    try:
        offset = int(i.offset)
        limit = int(i.limit)
    except ValueError:
        return []

    (subject_type, key, full_key, q) = read_subject(path_info)
    solr_select = solr_select_url + "?version=2.2&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=key,author_name,author_key,title,edition_count,ia,cover_edition_key,has_fulltext&qt=standard&wt=json" % (q, offset, limit)
    solr_select += "&sort=edition_count+desc"
    reply = json.load(urllib.urlopen(solr_select))

    works = []
    for doc in reply['response']['docs']:
        w = {
            'key': '/works/' + doc['key'],
            'edition_count': doc['edition_count'],
            'title': doc['title'],
            'authors': [{'key': '/authors/' + k, 'name': n} for k, n in zip(doc['author_key'], doc['author_name'])],
        } 
        if 'cover_edition_key' in doc:
            w['cover_edition_key'] = doc['cover_edition_key']
        if doc.get('has_fulltext', None):
            w['has_fulltext'] = doc['has_fulltext']
            w['ia'] = doc['ia'][0]
        works.append(w)
    return json.dumps(works)

def work_object(w):
    obj = dict(
        authors = [web.storage(key='/authors/' + k, name=n) for k, n in zip(w['author_key'], w['author_name'])],
        edition_count = w['edition_count'],
        key = '/works/' + w['key'],
        title = w['title'],
        cover_edition_key = w.get('cover_edition_key', None),
        first_publish_year = (w['first_publish_year'][0] if 'first_publish_year' in w else None),
        ia = w.get('ia', [])
    )
    if w.get('has_fulltext', None):
        obj['has_fulltext'] = w['has_fulltext']
    return web.storage(obj)

def get_facet(facets, f, limit=None):
    return list(web.group(facets[f][:limit * 2] if limit else facets[f], 2))

def build_get_subject_facet(facets, subject_type, name_index):
    def get_subject_facet(facet='subjects', limit=10):
        subjects = []
        i = subject_types[facet]
        if subject_type == i:
            num = 0
            for s in get_facet(facets, i + '_facet', limit=limit+1):
                if num != name_index:
                    subjects.append(s)
                num += 1
        else:
            subjects = get_facet(facets, i + '_facet', limit=limit)
        start = '/subjects/'
        if facet != 'subjects':
            start += facet + '/'
        return (web.storage(key=start + str_to_key(s).replace(' ', '_'), name=s, count=c) for s, c in subjects)
    return get_subject_facet

re_covers_json = re.compile('^(.+)/covers$')
class subjects(delegate.page):
    path = '/subjects/(.+)'
    def GET(self, path_info):
        m = re_covers_json.match(path_info)
        if m:
            return subjects_covers(m.group(1))
        limit = 12 * 3
        offset = 0
        if not path_info:
            return 'subjects page goes here'
        (subject_type, key, full_key, q) = read_subject(path_info)
        # q = ' AND '.join('subject_key:"%s"' % url_quote(key.lower().replace('_', ' ')) for key in path_info.split('+'))
        solr_select = solr_select_url + "?version=2.2&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=key,author_name,author_key,title,edition_count,ia,cover_edition_key,has_fulltext,first_publish_year&qt=standard&wt=json" % (q, offset, limit)
        facet_fields = ["author_facet", "language", "publish_year", "publisher_facet", "subject_facet", "person_facet", "place_facet", "time_facet"]
        solr_select += "&sort=edition_count+desc"
        solr_select += "&facet=true&facet.mincount=1&f.author_facet.facet.sort=count&f.publish_year.facet.limit=-1&facet.limit=25&" + '&'.join("facet.field=" + f for f in facet_fields)
        print solr_select
        reply = json.load(urllib.urlopen(solr_select))
        facets = reply['facet_counts']['facet_fields']
        def get_author(a, c):
            k, n = eval(a)
            return web.storage(key='/authors/' + k, name=n, count=c)

        def find_name_index (facets, key, subject_type):
            i = 0
            for name, count in web.group(facets[subject_type + '_facet'], 2):
                if str_to_key(name) == key:
                    return i, name, count
                i += 1

        def get_authors(limit=10):
            return (get_author(a, c) for a, c in get_facet(facets, 'author_facet', limit=limit))

        works = [work_object(w) for w in reply['response']['docs']]

        def get_covers(limit=20):
            collect = []
            for w in works if limit is None else works[:limit]:
                i = {
                    'key': w.key,
                    'title': w.title,
                    'authors': [dict(a) for a in w.authors],
                    'edition_count': w.edition_count,
                } 
                if w.get('cover_edition_key', None):
                    i['cover_edition_key'] = w.cover_edition_key
                if w.get('has_fulltext', None):
                    i['has_fulltext'] = w['has_fulltext']
                    i['ia'] = w['ia'][0]
                collect.append(i)
            return collect

        name_index, name, count = find_name_index(facets, key, subject_type)

        page = web.storage(
            key = full_key,
            name = name,
            work_count = count,
            works = works,
            get_covers = get_covers,
            subject_type = subject_type,
            authors = get_authors,
            author_count = None,
            publishers = (web.storage(name=k, count=v) for k, v in get_facet(facets, 'publisher_facet')),
            years = [(int(k), v) for k, v in get_facet(facets, 'publish_year')],
            subjects = build_get_subject_facet(facets, subject_type, name_index),
        )
        return render.subjects(page)

class search(delegate.page):
    def GET(self):
        i = web.input(author_key=[], language=[], first_publish_year=[], publisher_facet=[], subject_facet=[], person_facet=[], place_facet=[], time_facet=[])

        params = {}
        need_redirect = False
        for k, v in i.items():
            if isinstance(v, list):
                if v == []:
                    continue
                clean = [b.strip() for b in v]
                if clean != v:
                    need_redirect = True
                if len(clean) == 1 and clean[0] == u'':
                    clean = None
            else:
                clean = v.strip()
                if clean == '':
                    need_redirect = True
                    clean = None
                if clean != v:
                    need_redirect = True
            params[k] = clean
        if need_redirect:
            raise web.seeother(web.changequery(**params))

        return render.work_search(i, do_search, get_doc)

def works_by_author(akey, sort='editions', offset=0, limit=1000):
    q='author_key:' + akey
    solr_select = solr_select_url + "?version=2.2&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=key,author_name,author_key,title,edition_count,ia,cover_edition_key,has_fulltext,first_publish_year&qt=standard&wt=json" % (q, offset, limit)
    facet_fields = ["author_facet", "language", "publish_year", "publisher_facet", "subject_facet", "person_facet", "place_facet", "time_facet"]
    if sort == 'editions':
        solr_select += '&sort=edition_count+desc'
    elif sort.startswith('old'):
        solr_select += '&sort=first_publish_year'
    elif sort.startswith('new'):
        solr_select += '&sort=first_publish_year+desc'
    elif sort.startswith('title'):
        solr_select += '&sort=title'
    solr_select += "&facet=true&facet.mincount=1&f.author_facet.facet.sort=count&f.publish_year.facet.limit=-1&facet.limit=25&" + '&'.join("facet.field=" + f for f in facet_fields)
    reply = json.load(urllib.urlopen(solr_select))
    facets = reply['facet_counts']['facet_fields']
    works = [work_object(w) for w in reply['response']['docs']]

    def get_facet(f, limit=None):
        return list(web.group(facets[f][:limit * 2] if limit else facets[f], 2))

    return web.storage(
        num_found = int(reply['response']['numFound']),
        works = works,
        years = [(int(k), v) for k, v in get_facet('publish_year')],
        get_facet = get_facet,
        sort = sort,
    )

def simple_search(q, offset=0, rows=20, sort=None):
    solr_select = solr_select_url + "?version=2.2&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=*%%2Cscore&qt=standard&wt=json" % (web.urlquote(q), offset, rows)
    if sort:
        solr_select += "&sort=" + web.urlquote(sort)

    return json.load(urllib.urlopen(solr_select))

def top_books_from_author(akey, rows=5, offset=0):
    q = 'author_key:(' + akey + ')'
    solr_select = solr_select_url + "?indent=on&version=2.2&q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=*                             %%2Cscore&qt=standard&wt=standard&explainOther=&hl=on&hl.fl=title" % (q, offset, rows)
    solr_select += "&sort=edition_count+desc"

    reply = urllib.urlopen(solr_select)
    root = parse(reply).getroot()
    result = root.find('result')
    if result is None:
        return []

    return [web.storage(
        key=doc.find("str[@name='key']").text,
        title=doc.find("str[@name='title']").text,
        edition_count=int(doc.find("int[@name='edition_count']").text),
    ) for doc in result]

def do_merge():
    return

class merge_authors(delegate.page):
    path = '/merge/authors'
    def GET(self):
        i = web.input(key=[], master=None)
        keys = []
        for key in i.key:
            if key not in keys:
                keys.append(key)
        errors = []
        if i.master == '':
            errors += ['you must select a master author record']
        if not keys:
            errors += ['no authors selected']
        return render.merge_authors(errors, i.master, keys, top_books_from_author, do_merge)

class improve_search(delegate.page):
    def GET(self):
        i = web.input(q=None)
        boost = dict((f, i[f]) for f in search_fields if f in i)
        return render.improve_search(search_fields, boost, i.q, simple_search)

class merge_author_works(delegate.page):
    path = "/authors/(OL\d+A)/merge-works"
    def GET(self, key):
        works = works_by_author(key)
    
class subject_search(delegate.page):
    path = '/search/subjects'
    def GET(self):
        def get_results(q, offset=0, limit=100):
            solr_select = solr_subject_select_url + "?q.op=AND&q=%s&fq=&start=%d&rows=%d&fl=name,type,count&qt=standard&wt=json" % (web.urlquote(q), offset, limit)
            solr_select += '&sort=count+desc'
            return json.loads(urllib.urlopen(solr_select).read())
        return render_template('search/subjects.tmpl', get_results)

class search_json(delegate.page):
    path = "/search"
    encoding = "json"
    
    def GET(self):
        i = web.input()
        if 'query' in i:
            query = simplejson.loads(i.query)
        else:
            query = i
        
        from openlibrary.utils.solr import Solr
        import simplejson
        
        solr = Solr("http://%s/solr/works" % solr_host)
        result = solr.select(query)
        web.header('Content-Type', 'application/json')
        return delegate.RawText(simplejson.dumps(result, indent=True))