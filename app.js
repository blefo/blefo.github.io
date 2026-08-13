(function () {
  "use strict";

  var faceArt = window.FACE_ART || null;

  function drawEye(grid, cx, cy, px, py) {
    if (cy < 1 || cy + 1 >= grid.length) return;

    for (var dy = -1; dy <= 1; dy++) {
      for (var dx = -2; dx <= 2; dx++) {
        var y = cy + dy;
        var x = cx + dx;
        if (y >= 0 && y < grid.length && x >= 0 && x < grid[y].length) {
          grid[y][x] = " ";
        }
      }
    }

    function put(y, x, s) {
      if (y < 0 || y >= grid.length) return;
      var row = grid[y];
      for (var i = 0; i < s.length; i++) {
        var col = x + i;
        if (col >= 0 && col < row.length) row[col] = s[i];
      }
    }

    put(cy - 1, cx - 2, "(   )");
    put(cy, cx - 2, "(   )");
    put(cy + 1, cx - 2, "(   )");

    var pupilRow = cy + Math.max(-1, Math.min(1, py - 1));
    var pupilCol = cx + Math.max(-1, Math.min(1, px - 1));
    if (pupilRow >= 0 && pupilRow < grid.length && pupilCol >= 0 && pupilCol < grid[pupilRow].length) {
      grid[pupilRow][pupilCol] = "o";
    }
  }

  function renderPhotoFace(pupilLX, pupilLY, pupilRX, pupilRY) {
    var grid = faceArt.lines.map(function (line) {
      return line.split("");
    });
    var eyes = faceArt.eyes || [];
    for (var i = 0; i < eyes.length; i++) {
      var eye = eyes[i];
      var px = i === 0 ? pupilLX : pupilRX;
      var py = i === 0 ? pupilLY : pupilRY;
      drawEye(grid, eye.x, eye.y, px, py);
    }
    return grid
      .map(function (row) {
        return row.join("").replace(/\s+$/, "");
      })
      .join("\n");
  }

  // Fallback portrait used when the generated face-art file is not loaded.
  function renderFace(pupilLX, pupilLY, pupilRX, pupilRY) {
    if (faceArt && faceArt.lines && faceArt.lines.length) {
      return renderPhotoFace(pupilLX, pupilLY, pupilRX, pupilRY);
    }

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

(function () {
  "use strict";

  if (window.matchMedia("(max-width: 760px)").matches) return;

  var canvas = document.getElementById("canvas");
  var items = Array.prototype.slice.call(document.querySelectorAll(".drag-item"));
  if (!canvas || !items.length) return;

  var STORAGE_KEY = "bl-portfolio-layout-v1";
  var saved = {};
  var state = {};

  try {
    saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}") || {};
  } catch (err) {
    saved = {};
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(value, max));
  }

  function save() {
    var out = {};
    items.forEach(function (el) {
      var s = state[el.dataset.dragId];
      if (s) out[el.dataset.dragId] = { x: s.x, y: s.y, w: s.w, h: s.h };
    });
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(out));
    } catch (err) {
      // Layout persistence is best-effort; dragging still works in-memory.
    }
  }

  function updateHeight() {
    var bottom = 0;
    items.forEach(function (el) {
      var s = state[el.dataset.dragId];
      if (s) bottom = Math.max(bottom, s.y + s.h);
    });
    canvas.style.height = Math.max(window.innerHeight, bottom + 70) + "px";
  }

  function clampAll() {
    items.forEach(function (el) {
      var s = state[el.dataset.dragId];
      if (!s) return;
      s.x = clamp(s.x, 0, Math.max(0, canvas.clientWidth - s.w));
      s.y = clamp(s.y, 0, Math.max(0, canvas.clientHeight - s.h));
      el.style.left = s.x + "px";
      el.style.top = s.y + "px";
    });
  }

  function initPositions() {
    canvas.classList.add("measuring");
    window.requestAnimationFrame(function () {
      var rect = canvas.getBoundingClientRect();
      var padLeft = parseFloat(window.getComputedStyle(canvas).paddingLeft) || 0;
      var padTop = parseFloat(window.getComputedStyle(canvas).paddingTop) || 0;

      items.forEach(function (el) {
        var id = el.dataset.dragId;
        var box = el.getBoundingClientRect();
        state[id] = {
          x: Math.round(box.left - rect.left - padLeft),
          y: Math.round(box.top - rect.top - padTop),
          w: Math.round(box.width),
          h: Math.round(box.height)
        };
      });

      canvas.classList.remove("measuring");
      canvas.classList.add("js-positioned");

      items.forEach(function (el, index) {
        var id = el.dataset.dragId;
        var s = state[id];
        var prior = saved[id];
        if (prior) {
          s.x = prior.x;
          s.y = prior.y;
          s.w = prior.w;
          s.h = prior.h;
        }
        el.style.width = s.w + "px";
        el.style.left = s.x + "px";
        el.style.top = s.y + "px";
        el.style.zIndex = String(index + 2);
      });

      updateHeight();
      clampAll();
      updateHeight();
      save();
    });
  }

  function attachDrag(el, index) {
    var id = el.dataset.dragId;
    var baseZ = index + 2;
    var suppressClick = false;

    el.addEventListener(
      "click",
      function (e) {
        if (suppressClick) {
          e.preventDefault();
          e.stopPropagation();
          suppressClick = false;
        }
      },
      true
    );

    el.addEventListener("pointerdown", function (e) {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      var s = state[id];
      if (!s) return;

      var startX = e.clientX;
      var startY = e.clientY;
      var originX = s.x;
      var originY = s.y;
      var pointerId = e.pointerId;
      var dragging = false;
      var moved = false;

      function onMove(ev) {
        var dx = ev.clientX - startX;
        var dy = ev.clientY - startY;

        if (!dragging && Math.abs(dx) + Math.abs(dy) > 5) {
          dragging = true;
          moved = true;
          el.classList.add("is-dragging");
          el.style.zIndex = "1000";
          try {
            el.setPointerCapture(pointerId);
          } catch (err) {
            // Pointer capture is optional; window listeners still track the drag.
          }
        }
        if (!dragging) return;

        ev.preventDefault();
        s.x = clamp(originX + dx, 0, Math.max(0, canvas.clientWidth - s.w));
        s.y = clamp(originY + dy, 0, Math.max(0, canvas.clientHeight - s.h));
        el.style.left = s.x + "px";
        el.style.top = s.y + "px";
        updateHeight();
      }

      function onUp() {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);

        if (dragging) {
          el.classList.remove("is-dragging");
          el.style.zIndex = String(baseZ);
          el.classList.add("settle");
          window.setTimeout(function () {
            el.classList.remove("settle");
          }, 620);
          clampAll();
          updateHeight();
          save();
        }

        if (moved) {
          suppressClick = true;
          window.setTimeout(function () {
            suppressClick = false;
          }, 80);
        }
      }

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    });
  }

  items.forEach(attachDrag);
  initPositions();

  window.addEventListener("resize", function () {
    clampAll();
    updateHeight();
  });
})();
