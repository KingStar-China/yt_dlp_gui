using System.Windows;
using System.Windows.Threading;

namespace YtDlpGui.App;

public partial class App : Application
{
    public App()
    {
        DispatcherUnhandledException += OnDispatcherUnhandledException;
    }

    private static void OnDispatcherUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        MessageBox.Show(
            $"程序遇到未处理错误：{e.Exception.Message}",
            "yt_dlp_gui Native",
            MessageBoxButton.OK,
            MessageBoxImage.Error);
        e.Handled = true;
        Current.Shutdown(-1);
    }
}
