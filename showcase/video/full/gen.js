// Capture one scene of the 60-second BOKRI walkthrough.
// Usage: node gen.js <0..6>
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const APP = process.env.APP || 'http://127.0.0.1:4173';
const REPORT = '/showcase/ai-procurement/.psr/reports/run-20260721-a8833fd01145cab7.html';
const SOURCE_URL = 'https://www.gov.uk/guidance/managing-technical-lock-in-in-the-cloud';
const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const OUT = path.join(__dirname, 'clips_raw');
const sceneId = Number(process.argv[2]);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const SCENES = {
  0: { kind: 'intro', name: 'intro' },
  1: { kind: 'report', name: 'hero', enter: '.hero' },
  2: { kind: 'report', name: 'overview', enter: '#overview' },
  3: { kind: 'report', name: 'findings', enter: '#findings' },
  4: { kind: 'report', name: 'recommendations', enter: '#recommendations' },
  5: { kind: 'report', name: 'review', enter: '#review' },
  6: { kind: 'outro', name: 'outro' },
};

if (!SCENES[sceneId]) {
  console.error('Usage: node gen.js <0..6>');
  process.exit(2);
}

fs.mkdirSync(OUT, { recursive: true });

function titleCardHtml(kind) {
  const intro = kind === 'intro';
  const eyebrow = intro ? 'PUBLIC SECTOR RESEARCH SKILL' : 'PUBLIC SECTOR RESEARCH';
  const title = intro
    ? '<span class="acrostic-line"><b>공</b><span>공분야 보고서를 작성할 때,</span></span><span class="acrostic-line"><b>공</b><span>신력 있는 자료를 찾아</span></span><span class="acrostic-line"><b>복</b><span>잡한 문제도 근거부터 척척 풀어주는</span></span><span class="acrostic-line"><b>리</b><span>서치 Skill</span></span>'
    : '공공분야에 적합한<br><em>근거가 확실한 리서치 스킬</em>';
  const deck = intro
    ? '공공복리 · BOKRI'
    : '공공복리 · BOKRI';
  const footer = intro ? 'EVIDENCE FIRST · REVIEWABLE BY DESIGN' : '공공분야 보고서 리서치 Skill';
  return `<!doctype html>
  <html lang="ko"><head><meta charset="utf-8"><style>
    :root{font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
    *{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#0d293b;color:#fff}
    body{display:grid;place-items:center}
    #card{position:relative;width:100%;height:100%;padding:118px 150px;display:flex;flex-direction:column;justify-content:center;
      background:radial-gradient(circle at 78% 22%,rgba(42,182,166,.24),transparent 30%),linear-gradient(135deg,#0b2537,#123f4d 58%,#0b6863);opacity:0;transform:scale(.985);transition:opacity .65s ease,transform 1.1s cubic-bezier(.2,.8,.2,1)}
    #card::before{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px);background-size:64px 64px;mask-image:linear-gradient(90deg,#000,transparent 88%)}
    #card::after{content:"";position:absolute;right:-110px;top:50%;width:680px;height:680px;border:1px solid rgba(170,236,225,.22);border-radius:50%;transform:translateY(-50%);box-shadow:0 0 0 88px rgba(170,236,225,.035),0 0 0 176px rgba(170,236,225,.025)}
    #card.show{opacity:1;transform:none}#card.out{opacity:0;transform:scale(1.025)}
    .eyebrow,.title,.deck,.proofs,.footer{position:relative;z-index:2;opacity:0;transform:translateY(22px);transition:opacity .65s ease,transform .75s cubic-bezier(.2,.8,.2,1)}
    .eyebrow{color:#aee6dd;font-size:24px;font-weight:800;letter-spacing:.16em}
    .title{margin:28px 0 22px;max-width:1400px;font-size:94px;line-height:1.08;letter-spacing:-.055em;font-weight:850}
    .title em{font-style:normal;color:#f3c469}
    .deck{max-width:1050px;color:#e3eff0;font-size:34px;line-height:1.55;font-weight:600;letter-spacing:-.025em}
    .proofs{display:flex;gap:14px;margin-top:48px}.proof{border:1px solid rgba(196,236,230,.34);background:rgba(255,255,255,.08);border-radius:999px;padding:13px 22px;font-size:20px;font-weight:750;color:#dff5f1}
    .footer{position:absolute;left:150px;bottom:78px;color:#b5d0d2;font-size:17px;font-weight:750;letter-spacing:.12em}
    #card.show .eyebrow{transition-delay:.12s}#card.show .title{transition-delay:.27s}#card.show .deck{transition-delay:.48s}#card.show .proofs{transition-delay:.68s}#card.show .footer{transition-delay:.85s}
    #card.show .eyebrow,#card.show .title,#card.show .deck,#card.show .proofs,#card.show .footer{opacity:1;transform:none}
    .intro .title{display:flex;flex-direction:column;gap:8px;margin-top:24px;font-size:54px;line-height:1.25;letter-spacing:-.04em}
    .intro .acrostic-line{display:flex;align-items:baseline;white-space:nowrap}
    .intro .acrostic-line b{display:inline-block;flex:0 0 1.08em;color:#f3c469;font-size:1.12em;font-weight:900;text-shadow:0 0 28px rgba(243,196,105,.22)}
    .intro .deck{color:#aee6dd;font-size:27px;font-weight:850;letter-spacing:.08em}
    .intro .proofs{display:none}
    .outro .proofs{display:none}.outro .deck{font-size:30px;color:#bce9e3}.outro .title{font-size:88px}
  </style></head><body><main id="card" class="${kind}"><div class="eyebrow">${eyebrow}</div><h1 class="title">${title}</h1><p class="deck">${deck}</p><div class="proofs"><span class="proof">공식 원문</span><span class="proof">근거 구간</span><span class="proof">업무 시사점</span></div><div class="footer">${footer}</div></main></body></html>`;
}

async function injectReportOverlay(page) {
  await page.evaluate(() => {
    const html = document.documentElement;
    const body = document.body;
    const make = (id) => {
      const element = document.createElement('div');
      element.id = id;
      html.appendChild(element);
      return element;
    };

    make('__shade');
    make('__caption');
    make('__cursor');

    const cameraStage = document.createElement('div');
    cameraStage.id = '__cameraStage';
    const fixedIds = new Set(['progress', 'scrim', 'drawer']);
    [...body.children].forEach((node) => {
      if (!fixedIds.has(node.id) && node.tagName !== 'SCRIPT') cameraStage.appendChild(node);
    });
    body.insertBefore(cameraStage, document.getElementById('scrim'));

    const style = document.createElement('style');
    style.textContent = `
      #__shade{position:fixed;inset:auto 0 0;height:220px;z-index:2147483644;pointer-events:none;opacity:0;transition:opacity .2s ease;background:linear-gradient(180deg,rgba(7,18,29,0),rgba(7,18,29,.86))}
      #__shade.on{opacity:1}
      #__caption{position:fixed;left:112px;right:112px;bottom:46px;z-index:2147483646;color:#fff;font:700 42px/1.35 -apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif;letter-spacing:-.025em;text-align:left;text-shadow:0 3px 16px rgba(0,0,0,.68);opacity:0;transform:translateY(7px);transition:opacity .2s ease,transform .2s ease;pointer-events:none}
      #__caption.on{opacity:1;transform:none}
      #__cursor{position:fixed;left:960px;top:540px;width:24px;height:24px;z-index:2147483647;opacity:0;pointer-events:none;transition:left .55s cubic-bezier(.4,0,.2,1),top .55s cubic-bezier(.4,0,.2,1),opacity .15s;background:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M5 2l15 9-7 1 4 8-3 1-4-8-5 5z' fill='%23112636' stroke='white' stroke-width='1.5'/></svg>") no-repeat;filter:drop-shadow(0 2px 4px rgba(0,0,0,.5))}
      .skip{display:none!important}
      #__cameraStage{position:relative;transform-origin:0 0;transition:transform .62s cubic-bezier(.4,0,.2,1);will-change:transform}
      #drawer.open{transform-origin:0 0;transition:transform .62s cubic-bezier(.4,0,.2,1);will-change:transform}
    `;
    html.appendChild(style);

    window.__capOn = (text) => {
      const caption = document.getElementById('__caption');
      caption.textContent = text;
      caption.classList.add('on');
      document.getElementById('__shade').classList.add('on');
    };
    window.__capSwap = async (text) => {
      const caption = document.getElementById('__caption');
      caption.classList.remove('on');
      await new Promise((resolve) => setTimeout(resolve, 210));
      caption.textContent = text;
      caption.classList.add('on');
    };
    window.__capOff = () => {
      document.getElementById('__caption').classList.remove('on');
      document.getElementById('__shade').classList.remove('on');
    };
    window.__cur = (x, y) => {
      const cursor = document.getElementById('__cursor');
      cursor.style.left = `${x - 4}px`;
      cursor.style.top = `${y - 2}px`;
      cursor.style.opacity = '1';
    };
    window.__cameraFocus = (x, y, scale, targetX, targetY) => {
      const documentX = window.scrollX + x;
      const documentY = window.scrollY + y;
      const translateX = targetX + window.scrollX - scale * documentX;
      const translateY = targetY + window.scrollY - scale * documentY;
      cameraStage.style.transform = `translate(${translateX}px,${translateY}px) scale(${scale})`;
      window.__cur(targetX, targetY);
    };
    window.__cameraReset = (x, y) => {
      cameraStage.style.transform = 'none';
      if (Number.isFinite(x) && Number.isFinite(y)) window.__cur(x, y);
    };
    window.__drawerFocus = (x, y, scale, targetY) => {
      const drawer = document.getElementById('drawer');
      const rect = drawer.getBoundingClientRect();
      const localX = x - rect.x;
      const localY = y - rect.y;
      const translateX = window.innerWidth - rect.x - scale * rect.width;
      const translateY = Math.min(0, targetY - scale * localY);
      const focusedX = rect.x + translateX + scale * localX;
      const focusedY = rect.y + translateY + scale * localY;
      drawer.style.transform = `translate(${translateX}px,${translateY}px) scale(${scale})`;
      window.__cur(focusedX, focusedY);
    };
    window.__drawerReset = (x, y) => {
      document.getElementById('drawer').style.transform = 'none';
      if (Number.isFinite(x) && Number.isFinite(y)) window.__cur(x, y);
    };
  });
}

async function injectSourceOverlay(page, captionText) {
  await page.evaluate(({ sourceUrl, captionText }) => {
    const html = document.documentElement;
    const body = document.body;
    const stage = document.createElement('div');
    stage.id = '__sourceStage';
    [...body.children].forEach((node) => {
      if (node.tagName !== 'SCRIPT') stage.appendChild(node);
    });
    body.prepend(stage);

    const bar = document.createElement('div');
    bar.id = '__sourceBar';
    bar.innerHTML = `<span class="__official">공식 출처</span><div id="__sourceAddress"><span>🔒</span>${sourceUrl}</div>`;
    html.appendChild(bar);

    const shade = document.createElement('div');
    shade.id = '__sourceShade';
    html.appendChild(shade);
    const caption = document.createElement('div');
    caption.id = '__sourceCaption';
    caption.textContent = captionText;
    html.appendChild(caption);
    const cursor = document.createElement('div');
    cursor.id = '__sourceCursor';
    html.appendChild(cursor);

    const style = document.createElement('style');
    style.textContent = `
      .govuk-cookie-banner,#global-cookie-message{display:none!important}
      #__sourceStage{position:relative;padding-top:78px;transform-origin:0 0;transition:transform .68s cubic-bezier(.4,0,.2,1);will-change:transform}
      #__sourceBar{position:fixed;inset:0 0 auto;height:78px;z-index:2147483647;display:flex;align-items:center;gap:18px;padding:0 36px;background:#f5f7f8;border-bottom:1px solid #c9d1d6;box-shadow:0 5px 18px rgba(0,0,0,.14);font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Noto Sans KR',sans-serif}
      #__sourceBar .__official{flex:none;border-radius:999px;background:#00703c;color:#fff;padding:9px 16px;font-size:18px;font-weight:850;letter-spacing:-.02em}
      #__sourceAddress{display:flex;align-items:center;gap:11px;min-width:0;width:min(1320px,calc(100vw - 240px));border:1px solid #b8c2c8;border-radius:12px;background:#fff;color:#172b36;padding:10px 18px;font-size:25px;font-weight:750;letter-spacing:-.025em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      #__sourceShade{position:fixed;inset:auto 0 0;height:220px;z-index:2147483644;pointer-events:none;background:linear-gradient(180deg,rgba(7,18,29,0),rgba(7,18,29,.88))}
      #__sourceCaption{position:fixed;left:112px;right:112px;bottom:46px;z-index:2147483646;color:#fff;font:700 42px/1.35 -apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Noto Sans KR',sans-serif;letter-spacing:-.025em;text-shadow:0 3px 16px rgba(0,0,0,.68)}
      #__sourceCursor{position:fixed;left:960px;top:540px;width:24px;height:24px;z-index:2147483647;opacity:0;pointer-events:none;transition:left .55s cubic-bezier(.4,0,.2,1),top .55s cubic-bezier(.4,0,.2,1),opacity .15s;background:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M5 2l15 9-7 1 4 8-3 1-4-8-5 5z' fill='%23112636' stroke='white' stroke-width='1.5'/></svg>") no-repeat;filter:drop-shadow(0 2px 4px rgba(0,0,0,.5))}
      .__source-highlight{background:#fff4c2!important;border-left:10px solid #d4351c!important;padding:18px 22px!important;box-shadow:0 0 0 10px #fff4c2,0 18px 42px rgba(0,0,0,.16)!important}
    `;
    html.appendChild(style);

    window.__sourceCur = (x, y) => {
      cursor.style.left = `${x - 4}px`;
      cursor.style.top = `${y - 2}px`;
      cursor.style.opacity = '1';
    };
    window.__sourceFocus = (x, y, scale, targetX, targetY) => {
      const documentX = window.scrollX + x;
      const documentY = window.scrollY + y;
      const translateX = targetX + window.scrollX - scale * documentX;
      const translateY = targetY + window.scrollY - scale * documentY;
      stage.style.transform = `translate(${translateX}px,${translateY}px) scale(${scale})`;
      window.__sourceCur(targetX, targetY);
    };
  }, { sourceUrl: SOURCE_URL, captionText });
}

function sourceHelpers(page) {
  const center = async (locator) => {
    const box = await locator.boundingBox();
    if (!box) throw new Error('Source element has no bounding box');
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  };
  const move = async (point, settle = 550) => {
    await page.evaluate(({ x, y }) => window.__sourceCur(x, y), point);
    await sleep(settle);
  };
  const focus = async (locator, scale, target = { x: 960, y: 470 }, settle = 1600) => {
    const point = await center(locator);
    await move(point, 300);
    await page.evaluate(({ point, scale, target }) => window.__sourceFocus(point.x, point.y, scale, target.x, target.y), { point, scale, target });
    await sleep(settle);
  };
  return { center, move, focus };
}

function helpers(page) {
  const center = async (locator) => {
    const box = await locator.boundingBox();
    if (!box) throw new Error('Element has no bounding box');
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  };
  const move = async (point, settle = 550) => {
    await page.evaluate(({ x, y }) => window.__cur(x, y), point);
    await sleep(settle);
  };
  const focus = async (locator, scale, target = { x: 960, y: 430 }, settle = 900) => {
    const point = await center(locator);
    await move(point, 280);
    await page.evaluate(({ point, scale, target }) => window.__cameraFocus(point.x, point.y, scale, target.x, target.y), { point, scale, target });
    await sleep(settle);
    return point;
  };
  const reset = async (point, settle = 480) => {
    await page.evaluate(({ x, y }) => window.__cameraReset(x, y), point);
    await sleep(settle);
  };
  const scrollTo = async (locator, settle = 850) => {
    await page.evaluate(() => window.__cameraReset());
    await sleep(260);
    await locator.evaluate((element) => element.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    await sleep(settle);
  };
  const focusDrawer = async (locator, scale, targetY, settle = 760) => {
    const point = await center(locator);
    await move(point, 260);
    await page.evaluate(({ point, scale, targetY }) => window.__drawerFocus(point.x, point.y, scale, targetY), { point, scale, targetY });
    await sleep(settle);
    return point;
  };
  const resetDrawer = async (point, settle = 430) => {
    await page.evaluate(({ x, y }) => window.__drawerReset(x, y), point);
    await sleep(settle);
  };
  return { center, move, focus, reset, scrollTo, focusDrawer, resetDrawer };
}

async function runReportScene(page, id) {
  const h = helpers(page);
  const cap = (text) => page.evaluate((value) => window.__capOn(value), text);
  const swap = (text) => page.evaluate((value) => window.__capSwap(value), text);

  if (id === 1) {
    await cap('검색은 끝났는데 근거가 안 보일 때가 있죠.');
    await sleep(550);
    await h.move(await h.center(page.locator('.hero h1')), 500);
    await h.focus(page.locator('.hero .meta'), 1.30, { x: 960, y: 500 }, 1900);
  }

  if (id === 2) {
    await cap('문장을 누르면 확인한 원문이 바로 열립니다.');
    await sleep(700);
    const cards = page.locator('#overview .summary-card');
    const sourceCard = cards.nth(2);
    await h.move(await h.center(sourceCard.locator('p')), 700);
    const firstChip = sourceCard.locator('.citation-chip').nth(1);
    const chipTarget = { x: 900, y: 455 };
    await h.focus(firstChip, 1.45, chipTarget, 1500);
    await page.mouse.click(chipTarget.x, chipTarget.y);
    await page.locator('#drawer.open').waitFor({ state: 'visible', timeout: 3000 });
    await sleep(280);
    await page.evaluate(() => window.__cameraReset());
    await sleep(450);
    await swap('출처와 원문 위치를 수집 시점과 함께 남깁니다.');
    await h.move(await h.center(page.locator('#drawer blockquote')), 1050);
    const officialLink = page.locator('#drawer .action').filter({ hasText: '공식 원문 열기' }).first();
    await page.evaluate(() => {
      const link = [...document.querySelectorAll('#drawer .action')].find((element) => element.textContent.includes('공식 원문 열기'));
      const preview = document.createElement('div');
      preview.id = '__sourceUrlPreview';
      preview.textContent = link.href;
      preview.style.cssText = 'margin:18px 0 10px;padding:15px 17px;border:2px solid #0b776f;border-radius:12px;background:#e9f7f5;color:#093f4d;font:800 18px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere';
      link.parentElement.before(preview);
    });
    const preview = page.locator('#__sourceUrlPreview');
    await h.focusDrawer(preview, 1.38, 405, 1900);
    await page.evaluate(() => document.getElementById('drawer').style.removeProperty('transform'));
    await sleep(500);
    await swap('공식 출처 링크를 열어 원문까지 직접 확인합니다.');
    await page.evaluate(() => {
      const link = [...document.querySelectorAll('#drawer .action')].find((element) => element.textContent.includes('공식 원문 열기'));
      link.target = '_self';
    });
    const linkPoint = await h.center(officialLink);
    await h.move(linkPoint, 800);
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 30000 }),
      page.mouse.click(linkPoint.x, linkPoint.y),
    ]);
    await page.locator('h1').filter({ hasText: 'Managing technical lock-in in the cloud' }).waitFor({ state: 'visible', timeout: 15000 });
    await injectSourceOverlay(page, '공식 출처 링크를 열어 원문까지 직접 확인합니다.');
    const source = sourceHelpers(page);
    await source.move(await source.center(page.locator('#__sourceAddress')), 900);
    await source.move(await source.center(page.locator('h1').filter({ hasText: 'Managing technical lock-in in the cloud' }).first()), 850);
    const original = page.locator('p').filter({ hasText: 'Assessing your cloud providers must not stop after procurement.' }).first();
    await original.evaluate((element) => {
      window.scrollTo({ top: window.scrollY + element.getBoundingClientRect().top - 360, behavior: 'auto' });
    });
    await sleep(500);
    await original.evaluate((element) => element.classList.add('__source-highlight'));
    await page.locator('#__sourceCaption').evaluate((element) => {
      element.textContent = '보고서에 인용된 문장을 공식 원문에서 그대로 확인합니다.';
    });
    await source.focus(original, 1.55, { x: 1040, y: 480 }, 3300);
    await sleep(6500);
    return;
  }

  if (id === 3) {
    await cap('리서치 결과에 따라 의사결정에 도움이 될 만한 시사점도 제안해 줍니다.');
    await sleep(650);
    const findingOne = page.locator('#findings .finding').nth(0).locator('h3');
    await h.scrollTo(findingOne, 450);
    await h.move(await h.center(findingOne), 550);
    const findingTwo = page.locator('#findings .finding').nth(1).locator('h3');
    await h.scrollTo(findingTwo, 450);
    await h.move(await h.center(findingTwo), 550);
    const implication = page.locator('#implications .summary-card').nth(2).locator('p');
    await h.scrollTo(implication, 550);
    await h.focus(implication, 1.34, { x: 960, y: 410 }, 2200);
  }

  if (id === 4) {
    await cap('리스크 요인도 꼼꼼하게 체크해 주고요.');
    await sleep(550);
    const cards = page.locator('#recommendations .summary-card');
    for (const index of [1, 3, 4]) {
      const text = cards.nth(index).locator('p');
      await h.scrollTo(text, 350);
      await h.move(await h.center(text), 420);
    }
    const skills = cards.nth(6).locator('p');
    await h.scrollTo(skills, 400);
    await h.focus(skills, 1.32, { x: 960, y: 420 }, 1500);
  }

  if (id === 5) {
    await cap('확보하지 못한 근거와 적용 한계도 숨기지 않습니다.');
    await sleep(550);
    const items = page.locator('#review .panel').first().locator('li');
    await h.scrollTo(items.nth(0), 450);
    await h.move(await h.center(items.nth(0)), 650);
    await h.scrollTo(items.nth(3), 450);
    await h.focus(items.nth(3), 1.32, { x: 960, y: 390 }, 1800);
  }

  await page.evaluate(() => window.__capOff());
  await sleep(700);
}

(async () => {
  const scene = SCENES[sceneId];
  const browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ bypassCSP: true, viewport: { width: 1920, height: 1080 }, recordVideo: { dir: OUT, size: { width: 1920, height: 1080 } } });
  const pageStartedAt = Date.now();
  const page = await context.newPage();
  const video = page.video();

  if (scene.kind === 'report') {
    await page.goto(APP + REPORT, { waitUntil: 'networkidle', timeout: 60000 });
    if (scene.enter === '.hero') await page.evaluate(() => window.scrollTo(0, 0));
    else await page.locator(scene.enter).scrollIntoViewIfNeeded();
    await sleep(450);
    await injectReportOverlay(page);
    if (sceneId === 1) {
      await page.evaluate(() => {
        document.documentElement.style.background = '#123f4d';
        document.body.style.background = '#123f4d';
        document.getElementById('__cameraStage').style.background = '#f3f6f5';
      });
    }
  } else {
    await page.setContent(titleCardHtml(scene.kind), { waitUntil: 'load' });
    await sleep(250);
  }

  const captureStartedAt = Date.now();
  if (scene.kind === 'report') {
    await runReportScene(page, sceneId);
  } else {
    await page.locator('#card').evaluate((element) => element.classList.add('show'));
    await sleep(5300);
    await page.locator('#card').evaluate((element) => element.classList.add('out'));
    await sleep(700);
  }
  const captureMs = Date.now() - captureStartedAt;
  const preRollMs = captureStartedAt - pageStartedAt;

  await context.close();
  const webm = await video.path();
  await browser.close();
  console.log(JSON.stringify({ sceneId, name: scene.name, preRollMs, captureMs, webm }));
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
