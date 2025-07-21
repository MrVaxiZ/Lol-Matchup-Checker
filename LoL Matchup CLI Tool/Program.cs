using GetTopMachupsForGivenChamps.Helpers;
using GetTopMachupsForGivenChamps.Props;
using GetTopMachupsForGivenChamps.Data;
using OpenQA.Selenium.Support.UI;
using OpenQA.Selenium.Chrome;
using OpenQA.Selenium;
using System.Collections.ObjectModel;
using System.Collections.Concurrent;
using System.CommandLine;
using System.Diagnostics;
using System.Text;

#pragma warning disable IDE0063, IDE0300, IDE0305

class Program
{
    static async Task Main(string[] args)
    {
        await new App().RunAsync(args);
    }
}

class App
{
    public async Task<int> RunAsync(string[] args)
    {
        var champOption = new Option<string[]>(
            name: "--champs",
            description: "List of champions you play.",
            parseArgument: result => result.Tokens.Select(t => t.Value).ToArray()
        )
        { IsRequired = true, AllowMultipleArgumentsPerToken = true };

        var laneOption = new Option<string>(
            name: "--lane",
            description: "Lane you want matchups for (e.g. top, mid, jungle)."
        )
        { IsRequired = true };

        var outputOption = new Option<string>(
            name: "--out",
            description: "Output Excel file path.",
            getDefaultValue: () => "Matchups.xlsx"
        );

        var rootCommand = new RootCommand("LoL Matchup CLI Tool");
        rootCommand.AddOption(champOption);
        rootCommand.AddOption(laneOption);
        rootCommand.AddOption(outputOption);

        rootCommand.SetHandler((string[] userChamps, string laneStr, string output) =>
        {
            Stopwatch sw = Stopwatch.StartNew();

            EnumLanes lane = ParamValidator.GetLane(laneStr);

            HashSet<string> laneChampions = GetLaneChamps(lane, CreateOptimizedOptions());

            string[] userChampsFixed = ParamValidator.FixAliasName(userChamps, laneChampions);

            if (ParamValidator.GetUserChamps(userChampsFixed, laneChampions))
                Console.WriteLine("All champions were recognized!");
            else
                Console.WriteLine("Some of your provided champions were unrecognized!");

            ConcurrentBag<Matchup> matchups = GetData(lane, laneChampions, userChampsFixed);

            //SaveDataLog(ref sw, ref matchups); // debug

            ExcelHandler excelHandler = new(userChampsFixed, laneChampions, matchups);
            excelHandler.CreateExcel(output);

            Console.WriteLine($"Excel saved to: {output}");
        }, champOption, laneOption, outputOption);

        return await rootCommand.InvokeAsync(args);
    }

    private static void SaveDataLog(
        ref Stopwatch sw, 
        ref ConcurrentBag<Matchup> matchups, 
        ref HashSet<string> laneChampions, 
        ref string[] myTopChamps)
    {
        StringBuilder sb = new();
        uint expectedMatchups = ((uint)myTopChamps.Length * (uint)laneChampions.Count) - (uint)myTopChamps.Length;

        foreach (Matchup matchup in matchups)
        {
            sb.AppendLine($"ChampPlaying : {matchup.ChampPlaying}");
            sb.AppendLine($"ChampAgainst : {matchup.ChampAgainst}");
            sb.AppendLine($"Matches      : {matchup.Matches}");
            sb.AppendLine($"WinRate      : {matchup.WinRate}");
            sb.AppendLine($"Rating       : {matchup.Rating}");
            sb.AppendLine("------------------------------------------");
        }
        sb.AppendLine($"Matchups Count : [{matchups.Count}]");
        sb.AppendLine($"Expected Matchups : [{expectedMatchups}]");

        if (matchups.Count != expectedMatchups)
        {
            int diff = (int)expectedMatchups - matchups.Count;
            sb.AppendLine($"Total of [{diff}] matchups are missing.");
        }

        sw.Stop();
        sb.AppendLine($"Program was running for : [{sw.Elapsed.Hours.ToString("D2")}:{sw.Elapsed.Minutes.ToString("D2")}:{sw.Elapsed.Seconds.ToString("D2")}]");

        if (!File.Exists("Matchups.txt"))
        {
            using (var f = File.Create("Matchups.txt"))
            {
                f.Close();
            }
        }
        File.WriteAllText("Matchups.txt", sb.ToString());
    }

    private static ConcurrentBag<Matchup> GetData(EnumLanes lane, HashSet<string> Champions, string[] myChamps)
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
                            url = url.Replace("@", job.ChampAgainst.ToLower());
                            url = url.Replace("#", job.ChampPlaying.ToLower());
                            driver.Navigate().GoToUrl(url);

                            Thread.Sleep(1000);

                            CheckForCookies(driver);

                            Thread.Sleep(1000);

                            ((IJavaScriptExecutor)driver).ExecuteScript("window.scrollBy(0, 100);");

                            Thread.Sleep(1000);

                            string matchesText = driver.FindElement(By.XPath("//div[text()='Matches']/preceding-sibling::div")).Text;
                            string winRateText = driver.FindElement(By.XPath("//div[text()='Win Rate']/preceding-sibling::div")).Text;

                            matchesText = matchesText.Replace(",", "").Replace(".", ""); // Adding ',' or '.' when num is over 999 is stupid but USA does it for some reason.
                            winRateText = KeepOnlyDigits(winRateText);

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

                            matchup.Rating = DetermineRating(matchup);
                            matchups.Add(matchup);

                            Console.WriteLine($"{matchup.ChampPlaying} vs {matchup.ChampAgainst} : [{matchup.WinRate}%] WR, [{matchup.Matches}] Matches");
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine($"{job.ChampPlaying} vs {job.ChampAgainst}: {ex.Message}, reenquing to try again...");
                            jobQueue.Enqueue(job); // When failed enqueue job back to try again.
                            Thread.Sleep(1000);
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

    private static string KeepOnlyDigits(string input)
    {
        return new string(input.Where(char.IsDigit).ToArray());
    }

    private static string? DetermineRating(Matchup matchup)
    {
        if (matchup.WinRate < 49.0)
        {
            return "-";
        }
        else if (matchup.WinRate >= 49.0 && matchup.WinRate <= 51.0)
        {
            return "S";
        }
        else if (matchup.WinRate > 51.0 && matchup.WinRate < 53.0)
        {
            return "+";
        }
        else if (matchup.WinRate >= 53.0 && matchup.WinRate < 55.0)
        {
            return "D";
        }
        else if (matchup.WinRate >= 55.0 && matchup.WinRate < 60.0)
        {
            return "D+";
        }
        else if (matchup.WinRate >= 60.0)
        {
            return "UD";
        }
        else
        {
            return null;
        }
    }

    private static HashSet<string> GetLaneChamps(EnumLanes lane, ChromeOptions options)
    {
        HashSet<string> champions = [];

        using (IWebDriver driver = new ChromeDriver(options))
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

    private static void CheckForCookies(IWebDriver driver)
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

    private static ReadOnlyCollection<IWebElement> GetRows(IWebDriver driver)
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
    private static ChromeOptions CreateOptimizedOptions()
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
        return options;
    }

    private static void HandleCrash(IWebDriver driver, Exception ex)
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
}
