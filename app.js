(function () {
  "use strict";

  // Pupils sit in a 3x3 socket interior, so each eye can look in 9 directions.
  function renderFace(pupilLX, pupilLY, pupilRX, pupilRY) {
    var W = 34;
    var H = 14;
    var g = [];
    for (var r = 0; r < H; r++) g.push(new Array(W).fill(" "));

    var left = 4;
    var right = 29;
    var top = 0;
    var bottom = 12;

    for (var x = left + 1; x < right; x++) g[top][x] = "_";
    for (x = left + 1; x < right; x++) g[bottom][x] = "_";
    g[top + 1][left] = "/";
    g[top + 1][right] = "\\";
    g[bottom - 1][left] = "\\";
    g[bottom - 1][right] = "/";
    for (var y = top + 2; y < bottom - 1; y++) {
      g[y][left] = "|";
      g[y][right] = "|";
    }

    var eyes = [
      { x: 9, y: 4 },
      { x: 19, y: 4 },
    ];
    var pupils = [
      { x: pupilLX, y: pupilLY },
      { x: pupilRX, y: pupilRY },
    ];

    for (var i = 0; i < eyes.length; i++) {
      var e = eyes[i];
      for (var ex = e.x; ex < e.x + 5; ex++) g[e.y][ex] = "_";
      for (ex = e.x; ex < e.x + 5; ex++) g[e.y + 4][ex] = "_";
      for (var row = 1; row <= 4; row++) {
        g[e.y + row][e.x] = "|";
        g[e.y + row][e.x + 4] = "|";
      }
      var p = pupils[i];
      g[e.y + 1 + p.y][e.x + 1 + p.x] = "o";
    }

    var mx = 15;
    var my = 10;
    g[my][mx] = "\\";
    g[my][mx + 1] = "_";
    g[my][mx + 2] = "_";
    g[my][mx + 3] = "_";
    g[my][mx + 4] = "/";

    return g
      .map(function (row) {
        return row.join("").replace(/\s+$/, "");
      })
      .join("\n");
  }

  var faceEl = document.getElementById("face");
  if (!faceEl) return;

  var pending = null;

  function draw(dx, dy) {
    var ox = Math.round(dx);
    var oy = Math.round(dy);
    var px = 1 + ox;
    var py = 1 + oy;
    faceEl.textContent = renderFace(px, py, px, py);
  }

  function onMove(event) {
    var rect = faceEl.getBoundingClientRect();
    var cx = rect.left + rect.width / 2;
    var cy = rect.top + rect.height / 2;
    var spanX = rect.width / 2 || 1;
    var spanY = rect.height / 2 || 1;

    var dx = Math.max(-1, Math.min(1, (event.clientX - cx) / spanX));
    var dy = Math.max(-1, Math.min(1, (event.clientY - cy) / spanY));

    if (pending) cancelAnimationFrame(pending);
    pending = requestAnimationFrame(function () {
      draw(dx, dy);
    });
  }

  window.addEventListener("mousemove", onMove);
  draw(0, 0);
})();
