import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  MERMAID_MIN_READABLE_HEIGHT,
  VIEWBOX_PAD,
  fitMermaidSvg,
  mermaidShouldScroll,
  paddedContentBox,
  parseViewBoxAttr,
  stripMermaidViewportLock,
  viewBoxNeedsCrop,
} from "../src/lib/mermaidSvg.ts";

function mockSvg({ viewBox, bbox, nodes = [] }) {
  const attrs = viewBox ? { viewBox } : {};
  const styleProps = {};
  return {
    attributes: attrs,
    style: {
      removeProperty(name) {
        delete styleProps[name];
      },
      set height(value) {
        styleProps.height = value;
      },
      set maxWidth(value) {
        styleProps.maxWidth = value;
      },
      set maxHeight(value) {
        styleProps.maxHeight = value;
      },
      set width(value) {
        styleProps.width = value;
      },
      set aspectRatio(value) {
        styleProps.aspectRatio = value;
      },
      get height() {
        return styleProps.height;
      },
      get maxWidth() {
        return styleProps.maxWidth;
      },
      get aspectRatio() {
        return styleProps.aspectRatio;
      },
    },
    children: [],
    getAttribute(name) {
      return attrs[name] ?? null;
    },
    setAttribute(name, value) {
      attrs[name] = String(value);
    },
    removeAttribute(name) {
      delete attrs[name];
    },
    getBBox() {
      return bbox;
    },
    querySelectorAll() {
      return nodes;
    },
    querySelector() {
      return nodes[0] ?? null;
    },
  };
}

describe("stripMermaidViewportLock", () => {
  it("drops mermaid width/height/max-width and sets width=100%", () => {
    const raw =
      '<svg viewBox="0 0 1400 80" width="1400" height="80" style="max-width: 1400px; color: red;"></svg>';
    const out = stripMermaidViewportLock(raw);
    assert.match(out, /width="100%"/);
    assert.doesNotMatch(out, /height=/);
    assert.doesNotMatch(out, /max-width/);
    assert.match(out, /style="color: red"/);
  });
});

describe("viewBoxNeedsCrop", () => {
  it("crops a tall canvas under a shallow LR strip (old 15% gate would miss modest slack)", () => {
    const viewBox = { x: 0, y: 0, w: 1400, h: 200 };
    const content = { x: 8, y: 8, w: 1360, h: 168 };
    // 168+24=192, 200*0.85=170 → old code refused to crop; leftover shell.
    assert.equal(viewBoxNeedsCrop(viewBox, content), true);
  });

  it("crops when mermaid viewBox is much taller than painted nodes", () => {
    assert.equal(
      viewBoxNeedsCrop({ x: 0, y: 0, w: 1400, h: 420 }, { x: 10, y: 10, w: 1360, h: 70 }),
      true,
    );
  });

  it("leaves a tight viewBox alone", () => {
    const box = { x: 0, y: 0, w: 800, h: 90 };
    assert.equal(viewBoxNeedsCrop(box, { x: VIEWBOX_PAD, y: VIEWBOX_PAD, w: 776, h: 66 }), false);
  });
});

describe("mermaidShouldScroll", () => {
  it("keeps a wide shallow chart at natural width so it can scroll", () => {
    assert.equal(mermaidShouldScroll(2400, 80, 700), true);
  });

  it("fills the column when scaled height stays readable", () => {
    assert.equal(mermaidShouldScroll(1200, 400, 700), false);
    assert.ok(400 * (700 / 1200) >= MERMAID_MIN_READABLE_HEIGHT);
  });
});

describe("fitMermaidSvg", () => {
  it("crops leftover viewBox height and hugs painted LR content", () => {
    const nodes = [
      {
        getBBox: () => ({ x: 12, y: 10, width: 1360, height: 160 }),
      },
    ];
    const svg = mockSvg({
      viewBox: "0 0 1400 420",
      bbox: { x: 0, y: 0, width: 1400, height: 420 },
      nodes,
    });
    const fitted = fitMermaidSvg(svg, 720);
    assert.equal(fitted, true);
    const next = parseViewBoxAttr(svg.getAttribute("viewBox"));
    const expected = paddedContentBox({ x: 12, y: 10, w: 1360, h: 160 });
    assert.ok(next);
    assert.equal(next.w, expected.w);
    assert.equal(next.h, expected.h);
    assert.ok(next.h < 220, "shallow LR chart must not keep a tall canvas");
    assert.equal(svg.getAttribute("width"), "100%");
    assert.equal(svg.style.aspectRatio, `${expected.w} / ${expected.h}`);
    assert.equal(svg.style.height, "auto");
  });

  it("uses natural width when a wide chart would shrink below readable height", () => {
    const nodes = [
      {
        getBBox: () => ({ x: 0, y: 0, width: 2400, height: 72 }),
      },
    ];
    const svg = mockSvg({
      viewBox: "0 0 2400 72",
      bbox: { x: 0, y: 0, width: 2400, height: 72 },
      nodes,
    });
    fitMermaidSvg(svg, 640);
    const box = paddedContentBox({ x: 0, y: 0, w: 2400, h: 72 });
    assert.equal(svg.getAttribute("width"), String(Math.ceil(box.w)));
    assert.equal(svg.style.maxWidth, "none");
  });
});
