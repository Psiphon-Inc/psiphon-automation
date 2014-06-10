;(function() {
'use strict';

var GRAPH_COUNT = 50;
var DATE_BASELINE = Date.parse('2013-12-25');
var MIN_TIME_MS = 2 * 24 * 60 * 60 * 1000;


$(function() {
  if (!supportsTemplate()) {
    alert('Your browser is rubbish. Use Chrome.');
    throw new Error('Your browser is rubbish. Use Chrome.');
  }

  $('#show-host-graph').submit(function(event) {
    event.preventDefault();
    showHostGraph();
  });

  if (window.location.search.indexOf('hostID=') >= 0) {
    var hostIDs = window.location.search.slice(
                      window.location.search.indexOf('hostID=') + 'hostID='.length)
                    .split('&')[0]
                    .split(',');

    if (!hostIDs) {
      alert('No host ID supplied');
      return;
    }

    loadHostsIndex()
      .then(function(hosts) {
        var hostsInfo = [];
        $.each(hostIDs, function(idx, hostID) {
          var matches = _.filter(hosts, function(host) { return host[0] === hostID; });
          if (matches.length === 0) {
            alert('Requested Host ID does not exist!');
            throw new Error('Requested Host ID does not exist!');
          }

          // There should only be one match

          matches[0].push('N/A');

          hostsInfo.push(matches[0]);
        });

        graphHosts(hostsInfo);
      });
  }
  else {
    loadHostsIndex()
      .then(regressAllHosts)
      .then(function(results) {
        // We want the results with the steepest negative slope at the front of the array
        results = results.sort(function(a, b) {
          // Returning 1 pushes `a` toward the end of the array, and vice versa for -1.

          if (isNaN(a[2])) {
            return 1;
          }
          else if (isNaN(b[2])) {
            return -1;
          }
          return (a[2] > b[2]) ? 1 : -1;
        });

        //console.log(results);

        graphHosts(results.slice(0, GRAPH_COUNT));
      });
  }
});


function loadHostsIndex() {
  return new Promise(function(resolve, reject) {
    $.getJSON('./data.json')
      .fail(function(xhr) {
        var error = new Error('Ajax failed for ./data.json: ' + textStatus);
        progress.error(error);
        reject(error);
      })
      .done(function(hosts) {
        resolve(hosts);
      });
  });
}


// Resolves promise with array of [[hostname, datapath, slope], ...]
function regressAllHosts(hosts) {
  return new Promise(function(resolve, reject) {
    var regressionPromises = $.map(hosts, regressHost);
    Promise.all(regressionPromises).then(function(results) {
      resolve(results);
    });
  });
}


// Resolves promise with tuple of [hostname, datapath, slope]
function regressHost(hostInfo) {
  return new Promise(function(resolve, reject) {
    progress.hostStart();

    $.get(hostInfo[1])
      .fail(function(jqXHR, textStatus) {
        var error = new Error('Ajax failed for ' + hostInfo[1] + ': ' + textStatus);
        progress.error(error);
        reject(error);
      })
      .done(function(rawData) {
        var baselineDate;

        rawData = rawData.split('\n');
        // The file typically ends with `\n`, so we'll have an empty entry at the end.
        if (!rawData[rawData.length-1]) {
          rawData.pop();
        }

        var data = $.map(rawData, function(entry) {
          entry = entry.split(',');
          var date = Date.parse(entry[0]);
          if (!baselineDate) {
            baselineDate = date;
          }
          date = date - baselineDate;

          var val = parseFloat(entry[1]);
          return [[date, val]];
        });

        var regressionResult = regression('linear', data);
        var slope = regressionResult.equation[0];

        // We want to exclude hosts without enough data
        if (data[data.length-1][0] < MIN_TIME_MS) {
          slope = NaN;
        }

        progress.hostComplete();

        resolve([hostInfo[0], hostInfo[1], slope]);
      });
  });
}


/*
hostsInfo is an array of tuples of [hostname, datapath, slope]
*/
function graphHosts(hostsInfo) {
  $.each(hostsInfo, function(idx, hostInfo) {
    graphHost(hostInfo);
  });
}


function graphHost(hostInfo) {
  return new Promise(function(resolve, reject) {
    var template = document.querySelector('#graph-template');
    var graphFragment = document.importNode(template.content, true);
    var graphDiv = graphFragment.querySelector('.graph');
    var graphDivId = hostInfo[0];
    graphDiv.setAttribute('id', graphDivId);
    document.body.appendChild(graphFragment);

    new Dygraph(document.getElementById(graphDivId), hostInfo[1], {
      labels: [ 'Datetime', 'Users' ],
      title: 'Concurrently connected users for ' + hostInfo[0] + ' (' + hostInfo[2] + ')',
      ylabel: 'Concurrent users',
      showRoller: true,
      rollPeriod: 1,
      includeZero: true
    });

    resolve();
  });
}


function Progress() {
  var totalHosts = 0;
  var progressHosts = 0;

  function hostStart() {
    totalHosts += 1;
    progressHosts += 1;
    writeMsg('Hosts loading: ' + progressHosts);
  }

  function hostComplete() {
    progressHosts -= 1;
    writeMsg('Hosts loading: ' + progressHosts);

    if (progressHosts <= 0) {
      writeMsg('Loaded. Total hosts: ' + totalHosts);
    }
  }

  function error(msg) {
    writeMsg(msg.toString());
  }

  function writeMsg(msg) {
    $('#load-progress').text(msg);

    // Try to force a redraw. Doesn't actually work.
    $(this).each(function(){
      var redraw = this.offsetHeight;
    });
  }

  this.hostStart = hostStart;
  this.hostComplete = hostComplete;
  this.error = error;
}
var progress = new Progress();


function addLoadProgress(msg) {
  $('#load-progress').append($('<div>').text(msg));
}


function supportsTemplate() {
  return 'content' in document.createElement('template');
}


function showHostGraph() {
  var hostID = $('#host-graph').val();
  window.location.href = window.location.origin + window.location.pathname +
                          '?hostID=' + hostID;
}

}());
