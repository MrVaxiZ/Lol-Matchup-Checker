namespace GetTopMachupsForGivenChamps.Data
{
    static class EndPoints
    {
        internal static Dictionary<EnumLanes, string> EndPointsChamps = new()
        {
            { EnumLanes.Top, "https://u.gg/lol/top-lane-tier-list" },
            { EnumLanes.Jng, "https://u.gg/lol/jungle-tier-list" },
            { EnumLanes.Mid, "https://u.gg/lol/mid-lane-tier-list" },
            { EnumLanes.Adc, "https://u.gg/lol/adc-tier-list" },
            { EnumLanes.Sup, "https://u.gg/lol/support-tier-list" }
        };

        internal static Dictionary<EnumLanes, string> EndPointsMatches = new()
        {
            { EnumLanes.Top, "https://u.gg/lol/champions/@/build/top?opp=#" },
            { EnumLanes.Jng, "https://u.gg/lol/champions/@/build/jungle?opp=#" },
            { EnumLanes.Mid, "https://u.gg/lol/champions/@/build/mid?opp=#" },
            { EnumLanes.Adc, "https://u.gg/lol/champions/@/build/adc?opp=#" },
            { EnumLanes.Sup, "https://u.gg/lol/champions/@/build/support?opp=#" }
        };
    }
}
