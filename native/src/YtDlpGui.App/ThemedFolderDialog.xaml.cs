using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;

namespace YtDlpGui.App;

public partial class ThemedFolderDialog : Window
{
    private string? _currentDirectory;

    public ThemedFolderDialog(string initialDirectory)
    {
        InitializeComponent();
        SourceInitialized += (_, _) => ThemeManager.ApplyWindowChrome(this);
        Loaded += (_, _) =>
        {
            if (!TryNavigate(initialDirectory))
            {
                ShowDrives();
            }
        };
    }

    public string? SelectedDirectory { get; private set; }

    private void ComputerButton_Click(object sender, RoutedEventArgs e) => ShowDrives();

    private void DownloadsButton_Click(object sender, RoutedEventArgs e)
    {
        var downloads = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            "Downloads");
        if (!TryNavigate(downloads))
        {
            _ = TryNavigate(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile));
        }
    }

    private void UpButton_Click(object sender, RoutedEventArgs e)
    {
        if (_currentDirectory is null)
        {
            return;
        }

        var parent = Directory.GetParent(_currentDirectory);
        if (parent is null)
        {
            ShowDrives();
        }
        else
        {
            _ = TryNavigate(parent.FullName);
        }
    }

    private void GoButton_Click(object sender, RoutedEventArgs e) => NavigateFromAddressBar();

    private void PathTextBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
        {
            NavigateFromAddressBar();
            e.Handled = true;
        }
    }

    private void FoldersList_MouseDoubleClick(object sender, MouseButtonEventArgs e)
    {
        NavigateToSelectedEntry();
    }

    private void FoldersList_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
        {
            NavigateToSelectedEntry();
            e.Handled = true;
        }
    }

    private void FoldersList_SelectionChanged(object sender, SelectionChangedEventArgs e) =>
        RefreshSelectedPath();

    private void SelectButton_Click(object sender, RoutedEventArgs e)
    {
        SelectedDirectory = (FoldersList.SelectedItem as FolderEntry)?.FullPath ?? _currentDirectory;
        if (string.IsNullOrWhiteSpace(SelectedDirectory) || !Directory.Exists(SelectedDirectory))
        {
            StatusTextBlock.Text = "请选择一个可访问的文件夹。";
            return;
        }

        DialogResult = true;
    }

    private void NavigateFromAddressBar()
    {
        var path = Environment.ExpandEnvironmentVariables(PathTextBox.Text.Trim());
        if (!TryNavigate(path))
        {
            PathTextBox.SelectAll();
            PathTextBox.Focus();
        }
    }

    private void NavigateToSelectedEntry()
    {
        if (FoldersList.SelectedItem is FolderEntry entry)
        {
            _ = TryNavigate(entry.FullPath);
        }
    }

    private bool TryNavigate(string path)
    {
        try
        {
            var fullPath = Path.GetFullPath(path);
            if (!Directory.Exists(fullPath))
            {
                StatusTextBlock.Text = $"目录不存在：{fullPath}";
                return false;
            }

            var entries = new DirectoryInfo(fullPath)
                .EnumerateDirectories()
                .OrderBy(directory => directory.Name, StringComparer.CurrentCultureIgnoreCase)
                .Select(directory => new FolderEntry("📁", directory.Name, directory.FullName))
                .ToArray();

            _currentDirectory = fullPath;
            PathTextBox.Text = fullPath;
            FoldersList.ItemsSource = entries;
            FoldersList.SelectedItem = null;
            StatusTextBlock.Text = entries.Length == 0
                ? "当前目录没有子文件夹。"
                : $"共 {entries.Length} 个子文件夹。";
            RefreshSelectedPath();
            return true;
        }
        catch (Exception exception) when (
            exception is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            StatusTextBlock.Text = $"无法打开目录：{exception.Message}";
            return false;
        }
    }

    private void ShowDrives()
    {
        FolderEntry[] entries;
        try
        {
            entries = DriveInfo.GetDrives()
                .Where(drive => drive.IsReady)
                .OrderBy(drive => drive.Name, StringComparer.OrdinalIgnoreCase)
                .Select(CreateDriveEntry)
                .ToArray();
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            entries = [];
            StatusTextBlock.Text = $"无法读取驱动器：{exception.Message}";
        }

        _currentDirectory = null;
        PathTextBox.Text = "此电脑";
        FoldersList.ItemsSource = entries;
        FoldersList.SelectedItem = null;
        if (entries.Length > 0)
        {
            StatusTextBlock.Text = $"共 {entries.Length} 个可用驱动器。";
        }

        RefreshSelectedPath();
    }

    private static FolderEntry CreateDriveEntry(DriveInfo drive)
    {
        string? volumeLabel;
        try
        {
            volumeLabel = drive.VolumeLabel;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            volumeLabel = null;
        }

        return new(
            "▣",
            string.IsNullOrWhiteSpace(volumeLabel) ? drive.Name : $"{drive.Name}  {volumeLabel}",
            drive.RootDirectory.FullName);
    }

    private void RefreshSelectedPath()
    {
        var path = (FoldersList.SelectedItem as FolderEntry)?.FullPath ?? _currentDirectory;
        SelectButton.IsEnabled = !string.IsNullOrWhiteSpace(path);
        SelectedPathTextBlock.Text = string.IsNullOrWhiteSpace(path)
            ? "请选择一个文件夹"
            : $"将使用：{path}";
    }

    private sealed record FolderEntry(string Icon, string Name, string FullPath);
}
