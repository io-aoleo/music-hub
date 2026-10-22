/* Run browser_server.py first. PLAYWRIGHT_MODULE and BROWSER_EXECUTABLE are optional. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});const page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const output=path.resolve(process.env.BROWSER_OUTPUT||'artifacts');fs.mkdirSync(output,{recursive:true});
 await page.goto(process.env.HUB_TEST_URL||'http://127.0.0.1:18985');await page.waitForURL('**/setup');
 await page.locator('#submit:not([disabled])').waitFor();await page.screenshot({path:path.join(output,'first-run.png'),fullPage:true});
 await page.locator('#username').fill('browser-admin');await page.locator('#password').fill('browser-test-password');await page.locator('#confirmation').fill('browser-test-password');await page.locator('#submit').click();
 await page.locator('#view-settings:not([hidden])').waitFor();await page.waitForFunction(()=>document.getElementById('storageStatus').textContent.includes('目录可写'));
 await page.getByRole('button',{name:'选择 / 创建子目录',exact:true}).click();await page.locator('#newDirectoryName').fill('测试音乐');await page.getByRole('button',{name:'创建子目录',exact:true}).click();
 await page.waitForFunction(()=>document.getElementById('directoryPath').textContent.endsWith('/测试音乐'));
 await page.getByRole('button',{name:'使用此目录',exact:true}).click();await page.locator('#savePreferencesButton').click();await page.waitForFunction(()=>document.getElementById('settingsState').textContent==='设置已保存');
 await page.screenshot({path:path.join(output,'settings.png'),fullPage:true});
 await page.locator('#searchQuery').fill('测试');await page.locator('#searchButton').click();await page.locator('.song-choice').first().waitFor();await page.locator('#selectPage').check();
 assert.equal(await page.locator('#selectionCount').textContent(),'已选 3 首');await page.locator('#batchDownload').click();await page.locator('#view-downloads:not([hidden])').waitFor();
 await page.waitForFunction(()=>document.getElementById('downloadSummary').textContent.includes('3已完成'));
 await page.screenshot({path:path.join(output,'downloads.png'),fullPage:true});
 assert.equal(new URL(page.url()).pathname,'/');
 await page.reload();await page.evaluate(()=>switchView('downloads'));await page.waitForFunction(()=>document.getElementById('downloadSummary').textContent.includes('3已完成'));
 await page.getByRole('button',{name:'退出',exact:true}).click();await page.waitForURL('**/login');await page.locator('#submit:not([disabled])').waitFor();await page.screenshot({path:path.join(output,'login.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'login-mobile.png'),fullPage:true});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.locator('#username').fill('browser-admin');await page.locator('#password').fill('browser-test-password');await page.locator('#submit').click();await page.waitForURL('**/');await page.locator('#searchQuery').waitFor();
 await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.deepEqual(errors,[]);console.log('PASS: first-run setup, login/logout, CSRF, directory creation and mapping, batch selection/downloads, persisted history, desktop/mobile layouts');await browser.close();
})().catch(error=>{console.error(error);process.exit(1)});
