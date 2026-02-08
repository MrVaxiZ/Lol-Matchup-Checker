using LoL_Matchup_CLI_Tool.Data;
using LoL_Matchup_CLI_Tool.Props;
using OpenQA.Selenium;
using OpenQA.Selenium.Chrome;
using OpenQA.Selenium.Support.UI;
using System.Collections.Concurrent;
using System.Collections.ObjectModel;

namespace LoL_Matchup_CLI_Tool.Helpers
{
    class Scraper
    {
        byte FailCounter = 0; // If it fails more than 20 then surely something is broken.

        internal ConcurrentBag<Matchup> GetData(EnumLanes lane, HashSet<string> Champions, string[] myChamps)
        {
            ConcurrentBag<Matchup> matchups = [];

            var jobs = from enemy in Champions
                       from myChamp in myChamps
                       select (ChampAgainst: enemy, ChampPlaying: myChamp);

            var jobQueue = new ConcurrentQueue<(string ChampAgainst, string ChampPlaying)>(jobs);

            int workers = 6; // 5 to 6 are safe numbers more will blow up selenium

            List<Thread> threads = [];

            for (int i = 0; i < workers; i++)
            {
                var t = new Thread(() =>
                {
                    var options = CreateOptimizedOptions();
                    using (IWebDriver driver = new ChromeDriver(options))
                    {
                        driver.Manage().Timeouts().PageLoad = TimeSpan.FromSeconds(20);
                        driver.Manage().Timeouts().ImplicitWait = TimeSpan.FromSeconds(5);

                        while (jobQueue.TryDequeue(out var job))
                        {
                            try
                            {
                                if (job.ChampAgainst == job.ChampPlaying) { continue; }

                                string url = EndPoints.EndPointsMatches[lane];
                                url = url.Replace("@", FixChampionEndPoint(job.ChampAgainst));
                                url = url.Replace("#", FixChampionEndPoint(job.ChampPlaying));
                                driver.Navigate().GoToUrl(url);

                                Thread.Sleep(100);

                                CheckForCookies(driver);

                                Thread.Sleep(100);

                                ((IJavaScriptExecutor)driver).ExecuteScript("window.scrollBy(0, 100);");

                                Thread.Sleep(100);

                                string matchesText = driver.FindElement(By.XPath("//div[text()='Matches']/preceding-sibling::div")).Text;
                                string winRateText = driver.FindElement(By.XPath("//div[text()='Win Rate']/preceding-sibling::div")).Text;

                                matchesText = matchesText.Replace(",", "").Replace(".", ""); // Adding ',' or '.' when num is over 999 is stupid but USA does it for some reason.
                                winRateText = ParamValidator.KeepOnlyDigits(winRateText);

                                // Making sure % is correctly parsed into double
                                switch (winRateText.Length)
                                {
                                    case 2:
                                        winRateText += ",00"; // ex. "50" + ",00" = "50,00"
                                        break;
                                    case 3:
                                    case 4:
                                        winRateText = winRateText.Insert(2, ",");
                                        break;
                                    default:
                                        break;
                                }

                                Matchup matchup = new()
                                {
                                    ChampAgainst = job.ChampAgainst,
                                    ChampPlaying = job.ChampPlaying,
                                    Matches = uint.Parse(matchesText),
                                    WinRate = Math.Round(100 - double.Parse(winRateText), 2)
                                };

                                ProccesData proccesData = new(matchup);

                                matchup.Rating = proccesData.GetMatchupRating();
                                matchups.Add(matchup);

                                Console.WriteLine($"{matchup.ChampPlaying} vs {matchup.ChampAgainst} : [{matchup.WinRate}%] WR, [{matchup.Matches}] Matches");
                                FailCounter = 0;
                            }
                            catch (Exception ex)
                            {
                                //++FailCounter;
                                if (FailCounter < 20)
                                {
                                    Console.WriteLine($"{job.ChampPlaying} vs {job.ChampAgainst}: {ex.Message}, FAILED attempt [{FailCounter}], reenquing to try again...");

                                    jobQueue.Enqueue(job); // When failed enqueue job back to try again unless it is failing for more than 20 times.
                                }
                                else
                                {
                                    Console.WriteLine($"{job.ChampPlaying} vs {job.ChampAgainst}: Impossible to get tried over 20 times. Skipping...");
                                }

                                Thread.Sleep(100);
                            }
                        }
                    }
                });
                t.Start();
                threads.Add(t);
            }

            foreach (var t in threads)
                t.Join();

            return matchups;
        }

        internal HashSet<string> GetLaneChamps(EnumLanes lane)
        {
            HashSet<string> champions = [];

            using (IWebDriver driver = new ChromeDriver(CreateOptimizedOptions()))
            {
                try
                {
                    driver.Manage().Timeouts().PageLoad = TimeSpan.FromSeconds(10);
                    driver.Manage().Timeouts().ImplicitWait = TimeSpan.FromSeconds(5);

                    string url = EndPoints.EndPointsChamps[lane];
                    driver.Navigate().GoToUrl(url);

                    CheckForCookies(driver);

                    ((IJavaScriptExecutor)driver).ExecuteScript("window.scrollBy(0, 100);");

                    Thread.Sleep(1000);

                    var champRows = GetRows(driver);

                    for (int i = 0; i < champRows.Count; i++)
                    {
                        var nameElement = champRows[i].FindElement(By.CssSelector("strong.champion-name"));
                        string name = (string)((IJavaScriptExecutor)driver).ExecuteScript("return arguments[0].innerText;", nameElement);
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
                catch (Exception ex)
                {
                    HandleCrash(driver, ex);
                }
            }

            return [];
        }

        private ReadOnlyCollection<IWebElement> GetRows(IWebDriver driver)
        {
            try
            {
                var wait = new WebDriverWait(driver, TimeSpan.FromSeconds(5));
                wait.Until(drv => drv.FindElements(By.CssSelector("div.rt-tr-group")).Count > 0);

                ((IJavaScriptExecutor)driver).ExecuteScript("window.scrollBy(0, 2000);");
                Thread.Sleep(500);

                // Get all rows
                ReadOnlyCollection<IWebElement> rankRows = driver.FindElements(By.CssSelector("div.rt-tr-group"));

                Console.WriteLine($"Found total of [{rankRows.Count}] champions.");
                return rankRows;
            }
            catch (Exception ex)
            {
                HandleCrash(driver, ex);
                return null;
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

        private ChromeOptions CreateOptimizedOptions()
        {
            var options = new ChromeOptions();
            options.AddArgument("--headless=new");
            options.AddArgument("--disable-gpu");
            options.AddArgument("--no-sandbox");
            options.AddArgument("--use-gl=swiftshader");
            options.AddArgument("--blink-settings=imagesEnabled=false");
            options.AddArgument("--disable-dev-shm-usage");
            options.AddArgument("--disable-background-timer-throttling");
            options.AddArgument("--disable-backgrounding-occluded-windows");
            options.AddArgument("--disable-renderer-backgrounding");
            options.AddArgument("--enable-unsafe-swiftshader");
            options.PageLoadStrategy = PageLoadStrategy.Eager;
            return options;
        }

        private void CheckForCookies(IWebDriver driver)
        {
            try
            {
                var consentBtn = driver.FindElement(By.CssSelector("button.fc-button.fc-cta-consent"));
                if (consentBtn.Displayed && consentBtn.Enabled)
                {
                    consentBtn.Click();
                    Thread.Sleep(100);
                    Console.WriteLine("Cookies Accepted!");
                }
            }
            catch (NoSuchElementException)
            {
                Console.WriteLine("No Cookies to click!");
            }
        }

        private string FixChampionEndPoint(string champ)
        {
            const string SCN1 = "Master Yi";
            const string ASCN1 = "masteryi";
            const string SCN2 = "Bel'Veth";
            const string ASCN2 = "belveth";
            const string SCN3 = "Kha'Zix";
            const string ASCN3 = "khazix";
            const string SCN4 = "Jarvan IV";
            const string ASCN4 = "jarvaniv";
            const string SCN5 = "Rek'Sai";
            const string ASCN5 = "reksai";
            const string SCN6 = "Nunu & Willump";
            const string ASCN6 = "nunu";
            const string SCN7 = "Dr. Mundo";
            const string ASCN7 = "drmundo";
            const string SCN8 = "Lee Sin";
            const string ASCN8 = "leesin";
            const string SCN9 = "Xin Zhao";
            const string ASCN9 = "xinzhao";
            const string SCN10 = "Kog'Maw";
            const string ASCN10 = "kogmaw";
            const string SCN11 = "Kai'Sa";
            const string ASCN11 = "kaisa";
            const string SCN12 = "Miss Fortune";
            const string ASCN12 = "missfortune";
            const string SCN13 = "Renata Glasc";
            const string ASCN13 = "renata";
            const string SCN14 = "Tahm Kench";
            const string ASCN14 = "tahmkench";
            const string SCN15 = "K'Sante";
            const string ASCN15 = "ksante";
            const string SCN16 = "Vel'Koz";
            const string ASCN16 = "velkoz";
            const string SCN17 = "Twisted Fate";
            const string ASCN17 = "twistedfate";
            const string SCN18 = "Cho'Gath";
            const string ASCN18 = "chogath";
            const string SCN19 = "Aurelion Sol";
            const string ASCN19 = "aurelionsol";


            if (champ == SCN1) { return ASCN1; }
            else if (champ == SCN2) { return ASCN2; }
            else if (champ == SCN3) { return ASCN3; }
            else if (champ == SCN4) { return ASCN4; }
            else if (champ == SCN5) { return ASCN5; }
            else if (champ == SCN6) { return ASCN6; }
            else if (champ == SCN7) { return ASCN7; }
            else if (champ == SCN8) { return ASCN8; }
            else if (champ == SCN9) { return ASCN9; }
            else if (champ == SCN10) { return ASCN10; }
            else if (champ == SCN11) { return ASCN11; }
            else if (champ == SCN12) { return ASCN12; }
            else if (champ == SCN13) { return ASCN13; }
            else if (champ == SCN14) { return ASCN14; }
            else if (champ == SCN15) { return ASCN15; }
            else if (champ == SCN16) { return ASCN16; }
            else if (champ == SCN17) { return ASCN17; }
            else if (champ == SCN18) { return ASCN18; }
            else if (champ == SCN19) { return ASCN19; }
            else { return champ; }
        }
    }
}
