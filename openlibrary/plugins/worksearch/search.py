"""Search utilities.
"""

from openlibrary.utils.solr import Solr
from infogami import config

_ACTIVE_SOLR: Solr | None = None


def get_solr():
    global _ACTIVE_SOLR
    if not _ACTIVE_SOLR:
        base_url = config.plugin_worksearch.get('solr_base_url')
        _ACTIVE_SOLR = Solr(base_url)
    return _ACTIVE_SOLR
