using System.IO;
using System.Runtime.InteropServices;
using System.Security;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using Microsoft.Win32;
using YtDlpGui.Core;

namespace YtDlpGui.App;

internal static class ThemeManager
{
    private const string PersonalizeRegistryPath =
        @"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize";
    private const int DwmwaUseImmersiveDarkMode = 20;
    private const int DwmwaUseImmersiveDarkModeBefore20H1 = 19;

    private static readonly ThemePalette DarkPalette = new(
        Window: "#15171B",
        Card: "#202329",
        Control: "#292D34",
        ControlHover: "#343941",
        Border: "#3A3F48",
        Text: "#F5F7FA",
        MutedText: "#AAB2BF",
        Accent: "#49C6E5",
        AccentHover: "#66D4ED",
        AccentText: "#111418",
        SelectionHover: "#37414A",
        Selection: "#315662",
        StateBadge: "#26333A",
        Footer: "#191C21",
        DangerText: "#FFD6D6",
        Danger: "#47282D",
        DangerHover: "#573139",
        DangerBorder: "#744047",
        SuccessSurface: "#26333A",
        WarningText: "#FFD27A",
        WarningSurface: "#3B3220");

    private static readonly ThemePalette LightPalette = new(
        Window: "#F4F6F9",
        Card: "#FFFFFF",
        Control: "#F7F9FC",
        ControlHover: "#E9EEF4",
        Border: "#CBD3DD",
        Text: "#18202A",
        MutedText: "#5D6978",
        Accent: "#0078D4",
        AccentHover: "#1688DC",
        AccentText: "#FFFFFF",
        SelectionHover: "#E7F1FA",
        Selection: "#CCE5F6",
        StateBadge: "#E5F4FA",
        Footer: "#FFFFFF",
        DangerText: "#A12036",
        Danger: "#FDECEF",
        DangerHover: "#F8DCE2",
        DangerBorder: "#D99AA7",
        SuccessSurface: "#E5F4FA",
        WarningText: "#7A4B00",
        WarningSurface: "#FFF4CE");

    public static AppTheme Preference { get; private set; } = AppTheme.System;

    public static bool IsDarkMode { get; private set; }

    public static void Apply(AppTheme preference)
    {
        Preference = Enum.IsDefined(preference) ? preference : AppTheme.System;
        IsDarkMode = Preference switch
        {
            AppTheme.Dark => true,
            AppTheme.Light => false,
            _ => IsSystemDarkMode(),
        };

        if (Application.Current is not { } application)
        {
            return;
        }

        ApplyPalette(application.Resources, IsDarkMode ? DarkPalette : LightPalette);
        foreach (Window window in application.Windows)
        {
            ApplyWindowChrome(window);
        }
    }

    public static void RefreshSystemTheme()
    {
        if (Preference == AppTheme.System)
        {
            Apply(AppTheme.System);
        }
    }

    public static void ApplyWindowChrome(Window window)
    {
        if (!OperatingSystem.IsWindows())
        {
            return;
        }

        var handle = new WindowInteropHelper(window).Handle;
        if (handle == IntPtr.Zero)
        {
            return;
        }

        var enabled = IsDarkMode ? 1 : 0;
        var result = DwmSetWindowAttribute(
            handle,
            DwmwaUseImmersiveDarkMode,
            ref enabled,
            Marshal.SizeOf<int>());
        if (result < 0)
        {
            _ = DwmSetWindowAttribute(
                handle,
                DwmwaUseImmersiveDarkModeBefore20H1,
                ref enabled,
                Marshal.SizeOf<int>());
        }
    }

    private static bool IsSystemDarkMode()
    {
        try
        {
            return Registry.GetValue(PersonalizeRegistryPath, "AppsUseLightTheme", 1) is int value
                && value == 0;
        }
        catch (Exception exception) when (
            exception is IOException or UnauthorizedAccessException or SecurityException)
        {
            return false;
        }
    }

    private static void ApplyPalette(ResourceDictionary resources, ThemePalette palette)
    {
        SetBrush(resources, "WindowBrush", palette.Window);
        SetBrush(resources, "CardBrush", palette.Card);
        SetBrush(resources, "ControlBrush", palette.Control);
        SetBrush(resources, "ControlHoverBrush", palette.ControlHover);
        SetBrush(resources, "BorderBrush", palette.Border);
        SetBrush(resources, "TextBrush", palette.Text);
        SetBrush(resources, "MutedTextBrush", palette.MutedText);
        SetBrush(resources, "AccentBrush", palette.Accent);
        SetBrush(resources, "AccentHoverBrush", palette.AccentHover);
        SetBrush(resources, "AccentTextBrush", palette.AccentText);
        SetBrush(resources, "SelectionHoverBrush", palette.SelectionHover);
        SetBrush(resources, "SelectionBrush", palette.Selection);
        SetBrush(resources, "StateBadgeBrush", palette.StateBadge);
        SetBrush(resources, "FooterBrush", palette.Footer);
        SetBrush(resources, "DangerTextBrush", palette.DangerText);
        SetBrush(resources, "DangerBrush", palette.Danger);
        SetBrush(resources, "DangerHoverBrush", palette.DangerHover);
        SetBrush(resources, "DangerBorderBrush", palette.DangerBorder);
        SetBrush(resources, "SuccessSurfaceBrush", palette.SuccessSurface);
        SetBrush(resources, "WarningTextBrush", palette.WarningText);
        SetBrush(resources, "WarningSurfaceBrush", palette.WarningSurface);

        resources[SystemColors.WindowBrushKey] = CreateBrush(palette.Window);
        resources[SystemColors.WindowTextBrushKey] = CreateBrush(palette.Text);
        resources[SystemColors.ControlBrushKey] = CreateBrush(palette.Control);
        resources[SystemColors.ControlTextBrushKey] = CreateBrush(palette.Text);
        resources[SystemColors.HighlightBrushKey] = CreateBrush(palette.Accent);
        resources[SystemColors.HighlightTextBrushKey] = CreateBrush(palette.AccentText);
        resources[SystemColors.GrayTextBrushKey] = CreateBrush(palette.MutedText);
        resources[SystemColors.MenuBrushKey] = CreateBrush(palette.Card);
        resources[SystemColors.MenuTextBrushKey] = CreateBrush(palette.Text);
        resources[SystemColors.InfoBrushKey] = CreateBrush(palette.Card);
        resources[SystemColors.InfoTextBrushKey] = CreateBrush(palette.Text);
    }

    private static void SetBrush(ResourceDictionary resources, string key, string color) =>
        resources[key] = CreateBrush(color);

    private static SolidColorBrush CreateBrush(string color)
    {
        var brush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(color));
        brush.Freeze();
        return brush;
    }

    private sealed record ThemePalette(
        string Window,
        string Card,
        string Control,
        string ControlHover,
        string Border,
        string Text,
        string MutedText,
        string Accent,
        string AccentHover,
        string AccentText,
        string SelectionHover,
        string Selection,
        string StateBadge,
        string Footer,
        string DangerText,
        string Danger,
        string DangerHover,
        string DangerBorder,
        string SuccessSurface,
        string WarningText,
        string WarningSurface);

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(
        IntPtr windowHandle,
        int attribute,
        ref int value,
        int size);
}
