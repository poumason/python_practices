import { writeFile } from 'fs';
const { Selector, ClientFunction } = require('testcafe');

fixture`test page`.page`https://www.google.com/`;

test('Test screenshot', async (t) => {
    // wait page be loaded
    await t.wait(1000 * 5);
    // take screenshot
    await t.takeScreenshot({
        path: "screenshots/home-screenshot.png",
        fullPage: true
    });

});
