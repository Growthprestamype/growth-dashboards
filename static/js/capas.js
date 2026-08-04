/* La "tuerca": enciende y apaga las capas de contexto de cada gráfica.
   No necesita configuración: descubre los grupos <g data-capa data-nombre>
   que dibuja core/charts.py y arma el menú solo. La elección se recuerda
   en el navegador. */
(function () {
  var CLAVE = "gd-capas";

  function leer() {
    try { return JSON.parse(localStorage.getItem(CLAVE) || "{}"); }
    catch (e) { return {}; }
  }
  function guardar(estado) {
    try { localStorage.setItem(CLAVE, JSON.stringify(estado)); } catch (e) {}
  }

  function aplicar(svg, estado) {
    svg.querySelectorAll("[data-capa]").forEach(function (g) {
      var visible = estado[g.dataset.capa] !== false;
      g.style.display = visible ? "" : "none";
    });
  }

  function montar(chart) {
    var svg = chart.querySelector("svg");
    if (!svg) return;
    var grupos = svg.querySelectorAll("[data-capa]");
    if (!grupos.length) return;

    var capas = [];
    var vistos = {};
    grupos.forEach(function (g) {
      var k = g.dataset.capa;
      if (!vistos[k]) {
        vistos[k] = true;
        capas.push({ clave: k, nombre: g.dataset.nombre || k });
      }
    });

    var estado = leer();
    aplicar(svg, estado);

    // La tuerca se cuelga del título de la gráfica, si existe.
    var titulo = chart.previousElementSibling;
    var host = (titulo && titulo.classList.contains("chart-title"))
      ? titulo : chart;

    var caja = document.createElement("span");
    caja.className = "capas";
    var btn = document.createElement("button");
    btn.className = "capas-btn";
    btn.type = "button";
    btn.setAttribute("aria-label", "Capas de la gráfica");
    btn.title = "Añadir o quitar capas del mes";
    btn.innerHTML =
      '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">' +
      '<circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" ' +
      'stroke-width="1.8"/><path fill="none" stroke="currentColor" ' +
      'stroke-width="1.8" stroke-linejoin="round" d="M12 3.6l1.5 2.2 2.6-.5.6 ' +
      '2.6 2.4 1.1-1 2.5 1 2.5-2.4 1.1-.6 2.6-2.6-.5L12 20.4l-1.5-2.2-2.6.5-.6' +
      '-2.6-2.4-1.1 1-2.5-1-2.5 2.4-1.1.6-2.6 2.6.5z"/></svg>';

    var menu = document.createElement("div");
    menu.className = "capas-menu";
    menu.hidden = true;
    menu.innerHTML = '<div class="capas-tit">Capas del mes</div>';

    capas.forEach(function (c) {
      var fila = document.createElement("label");
      fila.className = "capas-fila";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = estado[c.clave] !== false;
      cb.addEventListener("change", function () {
        var e = leer();
        e[c.clave] = cb.checked;
        guardar(e);
        document.querySelectorAll(".chart svg").forEach(function (s) {
          aplicar(s, e);
        });
      });
      fila.appendChild(cb);
      fila.appendChild(document.createTextNode(" " + c.nombre));
      menu.appendChild(fila);
    });

    btn.addEventListener("click", function (ev) {
      ev.stopPropagation();
      menu.hidden = !menu.hidden;
    });
    document.addEventListener("click", function () { menu.hidden = true; });
    menu.addEventListener("click", function (ev) { ev.stopPropagation(); });

    caja.appendChild(btn);
    caja.appendChild(menu);
    host.appendChild(caja);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".chart").forEach(montar);
  });
})();

/* El embudo: despliega el menú de filtros de la data histórica. */
(function () {
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".embudo").forEach(function (caja) {
      var btn = caja.querySelector(".embudo-btn");
      var menu = caja.querySelector(".embudo-menu");
      if (!btn || !menu) return;
      btn.addEventListener("click", function (ev) {
        ev.stopPropagation();
        menu.hidden = !menu.hidden;
      });
      menu.addEventListener("click", function (ev) { ev.stopPropagation(); });
      document.addEventListener("click", function () { menu.hidden = true; });
    });
  });
})();
