using System.IO;
using System.Windows;
using System.Windows.Threading;
using YtDlpGui.Core;
using YtDlpGui.Infrastructure;

namespace YtDlpGui.App;

public partial class App : Application
{
    public App()
    {
        DispatcherUnhandledException += OnDispatcherUnhandledException;
    }

    protected override void OnStartup(StartupEventArgs e)
    {
        var theme = AppTheme.System;
        try
        {
            theme = new JsonSettingsStore().LoadAsync().GetAwaiter().GetResult().Theme;
        }
        catch (Exception exception) when (
            exception is IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            // A damaged or inaccessible settings file must not prevent the UI from starting.
        }

        ThemeManager.Apply(theme);
        base.OnStartup(e);
    }

    private static void OnDispatcherUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        var message = $"程序遇到未处理错误：{e.Exception.Message}";
        try
        {
            ThemedMessageDialog.Show(Current.MainWindow, "yt_dlp_gui Native", message, isSuccess: false);
        }
        catch
        {
            MessageBox.Show(
                message,
                "yt_dlp_gui Native",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }

        e.Handled = true;
        Current.Shutdown(-1);
    }
}
