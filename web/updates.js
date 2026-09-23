(() => {
  const status = document.querySelector('#updateStatus');
  const check = document.querySelector('#checkUpdate');
  const install = document.querySelector('#installUpdate');
  async function refresh(manual = false) {
    check.disabled = true;
    status.textContent = '正在检查 GitHub 最新版本…';
    try {
      const {result} = await api('/api/updates');
      status.textContent = result.available ? `当前 ${result.current_version} · 新版 ${result.version} 可下载` : `当前 ${result.current_version} · 已是最新版本`;
      install.hidden = !result.available;
      if (result.available) toast(`发现新版 ${result.version}，可在工具页下载更新`);
    } catch (error) {
      status.textContent = error.message;
      if (manual) toast(error.message, true);
    } finally { check.disabled = false; }
  }
  check.addEventListener('click', () => refresh(true));
  install.addEventListener('click', async () => {
    install.disabled = check.disabled = true;
    status.textContent = '正在下载并校验安装包，请稍候…';
    try {
      const {result} = await api('/api/updates/download', {});
      status.textContent = result.message;
    } catch (error) { status.textContent = error.message; }
    finally { install.disabled = check.disabled = false; }
  });
  refresh();
})();
