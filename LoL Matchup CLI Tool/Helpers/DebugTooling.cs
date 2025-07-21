using LoL_Matchup_CLI_Tool.Props;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text;

namespace LoL_Matchup_CLI_Tool.Helpers
{
    static class DebugTooling
    {
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
    }
}
