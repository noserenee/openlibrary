import fromPairs from 'lodash/fromPairs';
import isUndefined from 'lodash/isUndefined';
import includes from 'lodash/includes';
import orderBy from 'lodash/orderBy';
import entries from 'lodash/entries';
import groupBy from 'lodash/groupBy';
import uniq from 'lodash/uniq';
import uniqBy from 'lodash/uniqBy';
import 'chart.js';
import 'chartjs-plugin-datalabels';

/**
 * @param {object} config 
 * @param {object[]} config.works
 * @param {object[]} config.authors
 * @param {string} config.lang
 * @param {string} config.charts_selector
 */
export function init(config) {
    Chart.scaleService.updateScaleDefaults('linear', { ticks: { beginAtZero: true, stepSize: 1 } });
    const authors_by_id = fromPairs(config.authors.map(a => [a.key, a]));

    function createWorkChart(config, chartConfig, container, canvas) {
        const grouped = {};
        const excluded = [];
        for (const work of config.works) {
            const item = getPath(work, chartConfig.key);
            if (!item || !item.filter(x => !isUndefined(x) && !includes(chartConfig.exclude, x)).length) {
                excluded.push(work);
                continue;
            }
            for (const s of item.filter(x => !isUndefined(x) && !includes(chartConfig.exclude, x))) {
                grouped[s] = grouped[s] || [];
                grouped[s].push(work);
            }
        }

        const bars = orderBy(entries(grouped), x => x[1].length, 'desc').slice(0, 20);
        canvas.height = bars.length * 20 + 5;
        canvas.width= 400;
        const chart = new Chart(canvas.getContext('2d'), {
            type: 'horizontalBar',
            data: {
                labels: bars.map(b => b[0]),
                datasets: [{
                    backgroundColor: 'rgb(255, 99, 132)',
                    borderColor: 'rgb(255, 99, 132)',
                    borderWidth: 0,
                    data: bars.map(b => b[1].length)
                }]
            },
            options: {
                responsive: false,
                legend: { display: false },
                scales: {
                    xAxes: [{ display: false }],
                    yAxes: [{ barPercentage: 1, gridLines: { display: false }, stacked: true }],
                },
                onClick: (e, [chartEl]) => {
                    if (chartEl) {
                        const bar = bars[chartEl._index];
                        document.querySelector('.selected-works--list').innerHTML = render_works_list(bar[1]);
                    } else {
                        document.querySelector('.selected-works--list').innerHTML = '';
                    }
                },
                plugins: {
                    datalabels: {
                        color: '#FFF',
                        anchor: 'end',
                        align: 'left',
                        offset: 0
                    }
                }
            }
        });

        $(render_excluded_works_list(excluded, config.works.length)).appendTo(container);
    }

    const SPARQL_FIELDS = [
        { name: 'ethnic_group', type: 'uri', relation: 'wdt:P172' },
        { name: 'sex', type: 'uri', relation: 'wdt:P21' },
        { name: 'dob', type: 'literal', relation: 'wdt:P569' },
        { name: 'country_of_citizenship', type: 'uri', relation: 'wdt:P27' },
        { name: 'country_of_birth', type: 'uri', relation: 'wdt:P19/wdt:P131*/wdt:P17' },
    ];

    function buildSparql(authors) {
        return `
            SELECT DISTINCT ?x ?xLabel ?olid
                ${
                    SPARQL_FIELDS.map(f => `?${f.name} ` + (f.type == 'uri' ? `?${f.name}Label ` : '')).join('')
                }
            WHERE {
              VALUES ?olids { ${authors.map(a => `"${a.key.split('/')[2]}"`).join(' ')} }
              ?x wdt:P648 ?olids;
                 wdt:P648 ?olid.

              ${
                SPARQL_FIELDS.map(f => `OPTIONAL { ?x ${f.relation} ?${f.name}. }`)
                .join('\n')
              }

              SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],${config.lang},en". }
            }
        `;
    }

    document.getElementById('wd-query-sample').href = 'https://query.wikidata.org/#' + encodeURIComponent(buildSparql(config.authors.slice(0, 20)));

    const wdPromise = fetch('https://query.wikidata.org/sparql?format=json', {
        method: 'POST',
        body: new URLSearchParams({query: buildSparql(config.authors)})
    })
    .then(r => r.json())
    .then(resp => {
        const bindings = resp.results.bindings;
        const grouped = groupBy(bindings, o => o.x.value.split('/')[4]);
        const records = entries(grouped).map(([qid, bindings]) => {
            const record = { qid, olids: uniq(bindings.map(x => x.olid.value)) };
            // { qid: Q123, olids: [ { value: }, {value: }], blah: [ {value:}, {value:} ], blahLabel: [{value:}, {value:},
            for (const {name, type} of SPARQL_FIELDS) {
                if (type == 'uri') {
                    // need to dedupe whilst keeping labels in mind
                    const deduped = uniqBy(
                        bindings
                        .filter(x => x[name])
                        .map(x => ({ [name]: x[name], [name + 'Label']: x[name + 'Label'] })),
                        x => x[name].value)
                    record[name] = deduped.map(x => x[name]);
                    record[name + 'Label'] = deduped.map(x => x[name + 'Label']);
                } else {
                    record[name] = uniqBy(bindings.map(x => x[name]), 'value');
                }
            }
            return record;
        });

        for (const record of records) {
            for (const olid of record.olids) {
                if (`/authors/${olid}` in authors_by_id) {
                    authors_by_id[`/authors/${olid}`].wd = record;
                }
            }
        }
    });

    // Add full authors to the works objects for easy reference
    for (const work of config.works) {
        work.authors = work.author_keys.map(key => authors_by_id[key]);
    }

    for (const container of document.querySelectorAll(config.charts_selector)) {
        const chartConfig = JSON.parse(container.dataset['config']);
        const canvas = document.createElement('canvas');
        container.append(canvas);

        if (chartConfig.type == 'work-chart') {
            createWorkChart(config, chartConfig, container, canvas);
        } else if (chartConfig.type == 'wd-chart') {
            wdPromise.then(() => createWorkChart(config, chartConfig, container, canvas));
        }
    }
}

/**
 * @param {object} obj 
 * @param {string} key 
 * @return {any}
 */
function getPath(obj, key) {
    function main(obj, [head, ...rest]) {
        if (typeof(obj) == 'undefined') return undefined;
        if (!head) return obj;
        if (head.endsWith('[]')) return obj[head.slice(0, -2)].flatMap(x => main(x, rest));
        else return main(obj[head], rest);
    }
    return main(obj, key.split('.'));
}
