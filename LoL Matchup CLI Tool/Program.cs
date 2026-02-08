using LoL_Matchup_CLI_Tool.Data;
using LoL_Matchup_CLI_Tool.Helpers;
using LoL_Matchup_CLI_Tool.Props;
using System.Collections.Concurrent;
using System.CommandLine;
using System.Diagnostics;
using Command = System.CommandLine.Command;

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
#if DEBUG
        Stopwatch sw = Stopwatch.StartNew();
#endif
        var rootCommand = new RootCommand("LoL Matchup CLI Tool");

        // -------- Subcommand: generate --------
        var champOption = new Option<string[]>(
            name: "--champs",
            description: "List of champions you play.",
            parseArgument: result => result.Tokens.Select(t => t.Value).ToArray()
        )
        { IsRequired = true, AllowMultipleArgumentsPerToken = true };

        var laneOption = new Option<string>(
            ["--lane", "--role"],
            description: "Lane you want matchups for (e.g. top, mid, jg)."
        )
        { IsRequired = false };

        var outputOption = new Option<string>(
            name: "--out",
            description: "Output Excel file path.",
            getDefaultValue: () => "Matchups.xlsx"
        );

        // -------- Subcommand: alias --------
        var aliasCommand = new Command("alias",
            "Lists all available aliases and champions they are reffering to.\n" +
            "Usage : 'LoL Matchup CLI Tool.exe' alias'");
        aliasCommand.SetHandler(() =>
        {
            foreach (string key in Aliases.ChampAliases.Keys)
            {
                Console.WriteLine($"Alias : '{key}', Champion : '{Aliases.ChampAliases[key]}'");
            }
        });

        var generateCommand = new Command("gen",
            "Main command that generates Excel file filled with matchups.\n" +
            "Usage : 'LoL Matchup CLI Tool.exe' gen --lane mid --champs vlad lb' (you can also use '--role' instad of '--role')");
        generateCommand.AddOption(champOption);
        generateCommand.AddOption(laneOption);
        generateCommand.AddOption(outputOption);
        generateCommand.SetHandler((string[] userChamps, string laneStr, string output) =>
        {
            EnumLanes lane = ParamValidator.GetLane(laneStr);

            Scraper scraper = new();

            HashSet<string> laneChampions = scraper.GetLaneChamps(lane);

            string[] userChampsFixed = ParamValidator.FixAliasName(userChamps, laneChampions);

            if (ParamValidator.GetUserChamps(userChampsFixed, laneChampions))
                Console.WriteLine("All champions were recognized!");
            else
                Console.WriteLine("Some of your provided champions were unrecognized!");

            if (userChampsFixed.Contains("Shaco"))
                Console.WriteLine("Kill yourself for playing this champion"); // That is not a request that's an order.

            ConcurrentBag<Matchup> matchups = scraper.GetData(lane, laneChampions, userChampsFixed);

            //DebugTooling.SaveDataLog(ref sw, ref matchups); // debug

            ExcelHandler excelHandler = new(userChampsFixed, laneChampions, matchups);
            excelHandler.CreateExcel(output);

#if DEBUG
            sw.Stop();
            Console.WriteLine($"Program was runnig for : " +
                $"[{sw.Elapsed.Hours.ToString("D2")}:{sw.Elapsed.Minutes.ToString("D2")}:{sw.Elapsed.Seconds.ToString("D2")}]");
#endif

        }, champOption, laneOption, outputOption);

        // -------- Add subcommands to root --------
        rootCommand.AddCommand(aliasCommand);
        rootCommand.AddCommand(generateCommand);

        return await rootCommand.InvokeAsync(args);
    }
}
