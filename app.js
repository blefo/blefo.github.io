(function () {
  "use strict";

  // A human face drawn with ASCII. Each pupil moves in a 3x3 socket interior,
  // so both eyes can look up/down and left/right to follow the cursor.
  function renderFace(pupilLX, pupilLY, pupilRX, pupilRY) {
    var W = 40;
    var H = 15;
    var g = [];
    var r, i;
    for (r = 0; r < H; r++) g.push(new Array(W).fill(" "));

    function put(y, x, s) {
      for (var j = 0; j < s.length; j++) g[y][x + j] = s[j];
    }

    // Hair (dome).
    put(0, 15, "~~~~~~~~");
    put(1, 12, "~~~~~~~~~~~~~~");
    put(2, 9, "~~~~~~~~~~~~~~~~~~~~");

    // Head outline.
    g[3][8] = "/";
    g[3][31] = "\\";
    g[4][7] = "/";
    g[4][32] = "\\";
    for (r = 5; r <= 11; r++) {
      g[r][6] = "|";
      g[r][33] = "|";
    }
    g[12][7] = "\\";
    g[12][32] = "/";
    g[13][8] = "\\";
    g[13][31] = "/";
    put(14, 10, "____________");

    // Eyebrows.
    put(5, 13, "___");
    put(5, 25, "___");

    // Eyes: 5-wide almond sockets with a 3x3 pupil interior.
    var eyes = [
      { x: 12, y: 6 },
      { x: 24, y: 6 },
    ];
    var pupils = [
      { x: pupilLX, y: pupilLY },
      { x: pupilRX, y: pupilRY },
    ];

    for (i = 0; i < eyes.length; i++) {
      var e = eyes[i];
      put(e.y, e.x, "(   )");
      put(e.y + 1, e.x, "(   )");
      put(e.y + 2, e.x, "(   )");
      var p = pupils[i];
      g[e.y + p.y][e.x + 1 + p.x] = "o";
    }

    // Nose.
    put(9, 20, "|");
    put(10, 20, "~");

    // Mouth.
    put(11, 16, "\\______/");

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
