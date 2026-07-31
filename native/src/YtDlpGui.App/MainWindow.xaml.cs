using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using Microsoft.Win32;

namespace YtDlpGui.App;

public partial class MainWindow : Window
{
    private readonly MainViewModel _viewModel;

    public MainWindow()
    {
        _viewModel = new();
        InitializeComponent();
        DataContext = _viewModel;
        Loaded += OnLoaded;
        SourceInitialized += (_, _) => EnableDarkTitleBar();
        Closing += (_, _) => _viewModel.Dispose();
        _viewModel.NotificationRequested += ShowNotification;
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        await _viewModel.InitializeAsync();
        UrlTextBox.Focus();
    }

    private async void PrimaryAction_Click(object sender, RoutedEventArgs e) =>
        await _viewModel.RunPrimaryActionAsync();

    private void Cancel_Click(object sender, RoutedEventArgs e) => _viewModel.CancelCurrentOperation();

    private async void UpdateYtDlp_Click(object sender, RoutedEventArgs e) =>
        await _viewModel.UpdateYtDlpAsync();

    private async void SaveCookie_Click(object sender, RoutedEventArgs e) =>
        await _viewModel.SaveManualCookieAsync();

    private async void ChooseOutputDirectory_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFolderDialog
        {
            Title = "选择视频输出目录",
            InitialDirectory = Directory.Exists(_viewModel.OutputDirectory)
                ? _viewModel.OutputDirectory
                : Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            Multiselect = false,
        };

        if (dialog.ShowDialog(this) == true)
        {
            await _viewModel.SetOutputDirectoryAsync(dialog.FolderName);
        }
    }

    private void OpenOutputDirectory_Click(object sender, RoutedEventArgs e)
    {
        if (!Directory.Exists(_viewModel.OutputDirectory))
        {
            ShowNotification(new("错误", "输出目录不存在，请重新选择。", false));
            return;
        }

        var startInfo = new ProcessStartInfo("explorer.exe") { UseShellExecute = true };
        startInfo.ArgumentList.Add(_viewModel.OutputDirectory);
        Process.Start(startInfo);
    }

    private void ShowNotification(NotificationRequest notification)
    {
        MessageBox.Show(
            this,
            notification.Message,
            notification.Title,
            MessageBoxButton.OK,
            notification.IsSuccess ? MessageBoxImage.Information : MessageBoxImage.Warning);
    }

    private void EnableDarkTitleBar()
    {
        if (!OperatingSystem.IsWindows())
        {
            return;
        }

        var handle = new WindowInteropHelper(this).Handle;
        var enabled = 1;
        _ = DwmSetWindowAttribute(handle, 20, ref enabled, sizeof(int));
    }

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr windowHandle, int attribute, ref int value, int size);
}
