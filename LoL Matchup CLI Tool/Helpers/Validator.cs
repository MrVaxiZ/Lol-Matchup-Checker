using GetTopMachupsForGivenChamps.Data;
using LoL_Matchup_CLI_Tool.Data;

namespace GetTopMachupsForGivenChamps.Helpers
{
    static class ParamValidator
    {
        internal static EnumLanes GetLane(string lane)
        {
            const string exMess = "Provide lane in correct format! ex.'top', 'jng', 'mid', 'adc' or 'sup'.";

            if (string.IsNullOrEmpty(lane))
            {
                throw new ArgumentNullException(exMess);
            }

            if (Enum.TryParse<EnumLanes>(lane, true, out EnumLanes enumLane))
            {
                return enumLane;
            }
            else
            {
                throw new ArgumentException(exMess);
            }
        }

        internal static bool GetUserChamps(string[] userChamps, HashSet<string> laneChampions)
        {
            if(userChamps == null || userChamps.Length <= 0)
            {
                throw new ArgumentNullException("Provide your champion picks in param '--champs <champion_name>'");
            }

            List<string> unrecognizedChamps = [];

            foreach (var champ in laneChampions) 
            {
                if(!userChamps.Any(x => x.Equals(champ, StringComparison.CurrentCultureIgnoreCase)))
                {
                    unrecognizedChamps.Add(champ);
                }
            }

            if (unrecognizedChamps.Count == 0)
            {
                return true;
            }

            Console.WriteLine("These champions were unrecognized : ");

            foreach (var champ in unrecognizedChamps)
            {
                Console.WriteLine($" - {champ}");
            }

            return false;
        }

        internal static string[] FixAliasName(string[] userChamps, HashSet<string> laneChampions)
        {
            string[] userChampsFixed = new string[userChamps.Length];

            for(int i = 0; i < userChamps.Length; ++i)
            {
                string fullChampName = Aliases.ChampAliases[userChamps[i]];

                if (laneChampions.Any(x => x.Equals(fullChampName, StringComparison.CurrentCultureIgnoreCase)))
                {
                    userChampsFixed[i] = fullChampName;
                }
                else
                {
                    userChampsFixed[i] = userChamps[i];
                }
            }
            return userChampsFixed;
        }
    }
}
