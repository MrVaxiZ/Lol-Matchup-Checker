using DocumentFormat.OpenXml.Bibliography;
using DocumentFormat.OpenXml.Spreadsheet;
using LoL_Matchup_CLI_Tool.Data;
using LoL_Matchup_CLI_Tool.Props;
using Microsoft.Playwright;
using OpenQA.Selenium;
using OpenQA.Selenium.BiDi.BrowsingContext;
using OpenQA.Selenium.Chrome;
using OpenQA.Selenium.Support.UI;
using System.Collections.Concurrent;
using System.Collections.ObjectModel;

namespace LoL_Matchup_CLI_Tool.Helpers
{
    class Scraper
    {
        internal async Task<ConcurrentBag<Matchup>> GetData(EnumLanes lane, HashSet<string> champions, string[] myChamps)
        {
            ConcurrentBag<Matchup> matchups = new();
            SemaphoreSlim throttle = new(15); // Worker Limit

            var playwright = await Playwright.CreateAsync();
            await using var browser = await playwright.Chromium.LaunchAsync(new() { Headless = true });
            var context = await browser.NewContextAsync();

            var jobs = from enemy in champions
                       from myChamp in myChamps
                       where enemy != myChamp
                       select (ChampAgainst: enemy, ChampPlaying: myChamp);

            List<Task> tasks = new();

            foreach (var job in jobs)
            {
                tasks.Add(Task.Run(async () =>
                {
                    int retries = 0;
                    const int maxRetries = 5;

                    while (retries < maxRetries)
                    {
                        await throttle.WaitAsync();
                        var page = await context.NewPageAsync();

                        try
                        {
                            string url = EndPoints.EndPointsMatches[lane]
                                .Replace("@", job.ChampAgainst.ToLower())
                                .Replace("#", job.ChampPlaying.ToLower());

                            await page.GotoAsync(url, new() { Timeout = 20000 });

                            await CheckForCookies(page);
                            await page.EvaluateAsync("window.scrollBy(0, 100);");

                            var matchesSelector = "//div[text()='Matches']/preceding-sibling::div";
                            var matchesLocator = page.Locator(matchesSelector);
                            string matchesText = await matchesLocator.First.InnerTextAsync();

                            var winRateSelector = "//div[text()='Win Rate']/preceding-sibling::div";
                            var winRateLocator = page.Locator(winRateSelector);
                            string winRateText = await winRateLocator.First.InnerTextAsync();

                            matchesText = matchesText.Replace(",", "").Replace(".", "");
                            winRateText = ParamValidator.KeepOnlyDigits(winRateText);

                            switch (winRateText.Length)
                            {
                                case 2: winRateText += ",00"; break;
                                case 3:
                                case 4: winRateText = winRateText.Insert(2, ","); break;
                            }

                            Matchup matchup = new()
                            {
                                ChampAgainst = job.ChampAgainst,
                                ChampPlaying = job.ChampPlaying,
                                Matches = uint.Parse(matchesText),
                                WinRate = Math.Round(100 - double.Parse(winRateText), 2)
                            };

                            matchup.Rating = new ProccesData(matchup).GetMatchupRating();
                            matchups.Add(matchup);

                            Console.WriteLine($"{matchup.ChampPlaying} vs {matchup.ChampAgainst} : [{matchup.WinRate}%] WR, [{matchup.Matches}] Matches");

                            await page.CloseAsync();
                            break; // success – exit retry loop
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine($"{job.ChampPlaying} vs {job.ChampAgainst} (try {retries + 1}/{maxRetries}): {ex.Message}");

                            var screen = await page.ScreenshotAsync();
                            string fileName = $"EXE_SS_{job.ChampPlaying}vs{job.ChampAgainst}_try{retries + 1}.png";
                            await File.WriteAllBytesAsync(fileName, screen);

                            await page.CloseAsync();
                            await Task.Delay(1000); // delay before retry
                            retries++;
                        }
                        finally
                        {
                            throttle.Release();
                        }
                    }
                }));
            }

            await Task.WhenAll(tasks);
            return matchups;
        }

        internal async Task<HashSet<string>> GetLaneChamps(EnumLanes lane)
        {
            HashSet<string> champions = [];

            var playwright = await Playwright.CreateAsync();
            var browser = await playwright.Chromium.LaunchAsync(new() { Headless = true });

            var context = await browser.NewContextAsync();
            var page = await context.NewPageAsync();

            await page.GotoAsync(EndPoints.EndPointsChamps[lane]);

            await CheckForCookies(page);

            await Scroll(page, 2000);

            var champRows = GetRowsAsync(page);

            for (int i = 0; i < champRows.Result.Count; i++)
            {
                ILocator nameElem = champRows.Result[i].Locator("strong.champion-name");
                string name = await nameElem.InnerTextAsync();
                champions.Add(name);

                Console.WriteLine($"[{i}] Found champion : '{name}'");
            }

            if (champions.Count > 0)
            {
                return champions;
            }
            else
            {
                return [];
            }
        }

        private async Task Scroll(IPage page, ushort value)
        {
            await page.EvaluateAsync($"window.scrollBy(0, {value});");
        }

        private async Task<IReadOnlyList<ILocator>> GetRowsAsync(IPage page)
        {
            try
            {
                // Wait until rows are loaded
                await page.WaitForSelectorAsync("div.rt-tr-group", new() { Timeout = 5000 });

                // Scroll to bottom to force-load everything
                await page.EvaluateAsync("window.scrollBy(0, 2000);");
                await Task.Delay(500); // optional small pause if you observe lazy-load

                // Get all row locators
                var rows = page.Locator("div.rt-tr-group");
                int rowCount = await rows.CountAsync();

                Console.WriteLine($"Found total of [{rowCount}] champions.");

                // Return as a list of individual locators
                List<ILocator> result = new();
                for (int i = 0; i < rowCount; ++i)
                    result.Add(rows.Nth(i));

                return result;
            }
            catch (PlaywrightException ex)
            {
                Console.WriteLine($"[ERROR] Failed to get rows: {ex.Message}");
                return [];
            }
        }


        private void HandleCrash(IWebDriver driver, Exception ex)
        {
            Console.WriteLine($"EXCEPTION : {ex.Message}");

            string timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss_fff");
            string htmlPath = $"_debug_{timestamp}.html";
            string pngPath = $"_debug_{timestamp}.png";

            lock (driver)
            {
                try
                {
                    string pageSource = string.Empty;
                    try
                    {
                        pageSource = driver.PageSource;
                    }
                    catch (ObjectDisposedException)
                    {
                        Console.WriteLine("[WARN] WebDriver is already disposed, can't get page source.");
                    }

                    if (!string.IsNullOrEmpty(pageSource))
                    {
                        File.WriteAllText(htmlPath, pageSource);
                        Console.WriteLine($"[INFO] Page source saved to {htmlPath}");
                    }
                }
                catch (Exception ioex)
                {
                    Console.WriteLine($"[WARN] Could not write HTML file: {ioex.Message}");
                }

                try
                {
                    Screenshot screenshot = null;
                    try
                    {
                        screenshot = ((ITakesScreenshot)driver).GetScreenshot();
                    }
                    catch (ObjectDisposedException)
                    {
                        Console.WriteLine("[WARN] WebDriver is already disposed, can't take screenshot.");
                    }

                    if (screenshot != null)
                    {
                        screenshot.SaveAsFile(pngPath);
                        Console.WriteLine($"[INFO] Screenshot saved to {pngPath}");
                    }
                }
                catch (Exception screenshotEx)
                {
                    Console.WriteLine($"[WARN] Could not save screenshot: {screenshotEx.Message}");
                }
            }

            try { driver.Close(); } catch { }
            try { driver.Quit(); } catch { }
            try { driver.Dispose(); } catch { }
        }

        private async Task CheckForCookies(IPage page)
        {
            try
            {
                var consentButton = page.Locator("button.fc-button.fc-cta-consent");

                if (await consentButton.IsVisibleAsync())
                {
                    await consentButton.ClickAsync();
                    Console.WriteLine("Cookies Accepted!");
                }
                else
                {
                    Console.WriteLine("No Cookies to click!");
                }
            }
            catch (TimeoutException)
            {
                Console.WriteLine("Cookies: timeout — button never appeared.");
            }
            catch (PlaywrightException ex)
            {
                Console.WriteLine($"[WARN] Cookie click failed : {ex.Message}");
            }
        }
    }
}
