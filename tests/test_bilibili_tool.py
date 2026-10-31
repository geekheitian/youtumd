import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import bilibili_tool as tool


def _frontmatter(markdown: str) -> dict:
    lines = markdown.splitlines()
    end = lines.index("---", 1)
    return yaml.safe_load("\n".join(lines[1:end]))


class BilibiliToolTests(unittest.TestCase):
    def test_normalize_space_url_adds_video_suffix(self):
        self.assertEqual(
            tool.normalize_space_url("https://space.bilibili.com/513194466"),
            "https://space.bilibili.com/513194466/video",
        )
        self.assertEqual(
            tool.normalize_space_url("https://space.bilibili.com/513194466/video"),
            "https://space.bilibili.com/513194466/video",
        )

    def test_parse_playlist_line_keeps_title_and_id(self):
        video = tool.parse_playlist_line("测试标题|BV1UKZtBNE42|20260317")
        self.assertEqual(video["title"], "测试标题")
        self.assertEqual(video["id"], "BV1UKZtBNE42")
        self.assertEqual(video["upload_date"], "20260317")

    def test_parse_playlist_line_keeps_title_with_pipes(self):
        video = tool.parse_playlist_line("A | B | C|BV1UKZtBNE42|20260317")
        self.assertEqual(video["title"], "A | B | C")
        self.assertEqual(video["id"], "BV1UKZtBNE42")

    def test_extract_subtitle_lines_from_json_reads_body_content(self):
        content = '{"body":[{"content":"第一句"},{"content":"第二句"}]}'
        self.assertEqual(tool.extract_subtitle_lines_from_json(content), ["第一句", "第二句"])

    def test_extract_subtitle_lines_from_text_strips_timestamps(self):
        content = """WEBVTT

1
00:00:00.000 --> 00:00:02.000
第一句

2
00:00:02.000 --> 00:00:04.000
第二句
"""
        self.assertEqual(tool.extract_subtitle_lines_from_text(content), ["第一句", "第二句"])

    def test_find_existing_summary_matches_bilibili_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = tool.load_config()
            config = config.__class__(
                base_dir=Path(tmpdir),
                content_subdir=config.content_subdir,
                default_channel_url=config.default_channel_url,
                default_channel_name=config.default_channel_name,
                default_limit=config.default_limit,
                minimax_base_url=config.minimax_base_url,
                minimax_model=config.minimax_model,
            )
            context = tool.build_space_context("https://space.bilibili.com/513194466/video", config)
            context.summaries_dir.mkdir(parents=True, exist_ok=True)
            summary_path = context.summaries_dir / "existing.md"
            summary_path.write_text(
                "---\nsource: https://www.bilibili.com/video/BV1UKZtBNE42\n---\n",
                encoding="utf-8",
            )

            match = tool.find_existing_summary("https://www.bilibili.com/video/BV1UKZtBNE42", context)
            self.assertEqual(match, summary_path)

    def test_save_summary_removes_old_noncanonical_file_on_force_retry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = tool.load_config()
            config = config.__class__(
                base_dir=Path(tmpdir),
                content_subdir=config.content_subdir,
                default_channel_url=config.default_channel_url,
                default_channel_name=config.default_channel_name,
                default_limit=config.default_limit,
                minimax_base_url=config.minimax_base_url,
                minimax_model=config.minimax_model,
            )
            context = tool.build_space_context("https://space.bilibili.com/513194466/video", config)
            context.summaries_dir.mkdir(parents=True, exist_ok=True)

            old_path = context.summaries_dir / "旧命名.md"
            old_path.write_text(
                "---\nsource: https://www.bilibili.com/video/BV1UKZtBNE42\n---\n",
                encoding="utf-8",
            )

            publish_dates = {"compact": "20260317", "display": "2026-03-17"}
            saved_path = tool.save_summary(
                "测试标题",
                "content",
                context,
                publish_dates,
                existing_summary=old_path,
            )

            expected_path = context.summaries_dir / "测试标题-20260317.md"
            self.assertEqual(Path(saved_path), expected_path)
            self.assertTrue(expected_path.exists())
            self.assertFalse(old_path.exists())

    def test_convert_raw_cookie_header_to_netscape(self):
        converted = tool.convert_raw_cookie_header_to_netscape("SESSDATA=abc; bili_jct=def")
        self.assertIn("# Netscape HTTP Cookie File", converted)
        self.assertIn("\tSESSDATA\tabc", converted)
        self.assertIn("\tbili_jct\tdef", converted)

    def test_is_raw_cookie_header_detects_single_line_cookie(self):
        self.assertTrue(tool.is_raw_cookie_header("SESSDATA=abc; bili_jct=def"))
        self.assertFalse(tool.is_raw_cookie_header("# Netscape HTTP Cookie File\n.example.com\tTRUE"))

    def test_summary_frontmatter_quotes_title_with_colon(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = tool.load_config()
            config = config.__class__(
                base_dir=Path(tmpdir),
                content_subdir=config.content_subdir,
                default_channel_url=config.default_channel_url,
                default_channel_name=config.default_channel_name,
                default_limit=config.default_limit,
                minimax_base_url=config.minimax_base_url,
                minimax_model=config.minimax_model,
            )
            context = tool.build_space_context("https://space.bilibili.com/513194466/video", config, override_name="测试频道")
            publish_dates = {"compact": "20260317", "display": "2026-03-17"}
            title = '课程: 第一讲'
            markdown = tool.build_summary_markdown(
                title,
                "https://www.bilibili.com/video/BV1UKZtBNE42",
                "BV1UKZtBNE42",
                "### 核心主题\n内容",
                "MiniMax",
                context,
                publish_dates,
            )
            loaded = _frontmatter(markdown)
            self.assertEqual(loaded["title"], title)
            self.assertEqual(loaded["source"], "https://www.bilibili.com/video/BV1UKZtBNE42")
            self.assertIn('title: "课程: 第一讲"', markdown)
            self.assertIn("source: https://www.bilibili.com/video/BV1UKZtBNE42\n", markdown)

    def test_extract_bilibili_video_id_and_classify_target(self):
        url = "https://www.bilibili.com/video/BV1UKZtBNE42/?spm_id_from=333"
        self.assertEqual(tool.extract_bilibili_video_id(url), "BV1UKZtBNE42")
        self.assertEqual(tool.classify_bilibili_target(url), "video")
        self.assertEqual(
            tool.extract_bilibili_video_id("https://www.bilibili.com/video/av170001"),
            "av170001",
        )
        self.assertEqual(
            tool.classify_bilibili_target("https://space.bilibili.com/50247550/video"),
            "space",
        )
        self.assertEqual(tool.classify_bilibili_target("https://b23.tv/abc"), "video")
        self.assertIsNone(tool.extract_bilibili_video_id("https://b23.tv/abc"))

    def test_single_video_context_uses_uploader_or_single(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = tool.load_config()
            config = config.__class__(
                base_dir=Path(tmpdir),
                content_subdir=config.content_subdir,
                default_channel_url=config.default_channel_url,
                default_channel_name=config.default_channel_name,
                default_limit=config.default_limit,
                minimax_base_url=config.minimax_base_url,
                minimax_model=config.minimax_model,
            )
            named = tool.build_single_video_context(
                {
                    "id": "BV1UKZtBNE42",
                    "title": "课程: 第一讲",
                    "upload_date": "20260317",
                    "channel": "另一个UP",
                    "channel_url": "https://space.bilibili.com/999",
                },
                config,
            )
            unknown = tool.build_single_video_context(
                {
                    "id": "BV1UKZtBNE42",
                    "title": "课程: 第一讲",
                    "upload_date": "",
                    "channel": "",
                    "channel_url": "",
                },
                config,
            )
            self.assertEqual(named.name, "另一个UP")
            self.assertNotEqual(named.name, config.default_channel_name)
            self.assertEqual(unknown.name, "single")
            self.assertEqual(unknown.url, "https://www.bilibili.com/video/BV1UKZtBNE42")

    def test_fetch_single_video_parses_json_and_rejects_space_url(self):
        payload = json.dumps({
            "id": "BV1UKZtBNE42",
            "title": "课程: 第一讲",
            "upload_date": "20260317",
            "uploader": "清华姜学长",
            "uploader_url": "https://space.bilibili.com/50247550",
        })
        with mock.patch("bilibili_tool.run_command", return_value=(payload, "", 0)) as run:
            video = tool.fetch_single_video(
                "https://www.bilibili.com/video/BV1UKZtBNE42",
                None,
                None,
            )
        self.assertEqual(video["id"], "BV1UKZtBNE42")
        self.assertEqual(video["title"], "课程: 第一讲")
        self.assertEqual(video["channel"], "清华姜学长")
        self.assertIn("-J", run.call_args.args[0])

        with mock.patch("bilibili_tool.run_command") as run:
            missing = tool.fetch_single_video("https://space.bilibili.com/50247550/video", None, None)
        self.assertIsNone(missing)
        run.assert_not_called()

    @mock.patch("bilibili_tool.process_video", return_value=True)
    @mock.patch("bilibili_tool.fetch_single_video")
    def test_main_url_mode_reuses_process_video(self, mock_fetch, mock_process):
        mock_fetch.return_value = {
            "title": "课程: 第一讲",
            "id": "BV1UKZtBNE42",
            "upload_date": "20260317",
            "channel": "某个UP",
            "channel_url": "https://space.bilibili.com/999",
        }
        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch("sys.argv", [
                 "bilibili_tool.py",
                 "--url", "https://www.bilibili.com/video/BV1UKZtBNE42",
                 "--base-dir", tmpdir,
                 "--dry-run",
             ]):
            tool.main()

            mock_process.assert_called_once()
            video, context = mock_process.call_args.args[:2]
            self.assertEqual(video["id"], "BV1UKZtBNE42")
            self.assertEqual(context.name, "某个UP")
            self.assertNotEqual(context.name, "清华姜学长")
            self.assertTrue(mock_process.call_args.kwargs["dry_run"])
            self.assertFalse(mock_process.call_args.kwargs["force"])
            self.assertTrue(context.summaries_dir.exists())
            self.assertTrue(str(context.summaries_dir).startswith(tmpdir))

    def test_main_url_conflicts_with_space_url(self):
        with mock.patch("sys.argv", [
            "bilibili_tool.py",
            "--url", "https://www.bilibili.com/video/BV1UKZtBNE42",
            "--space-url", "https://space.bilibili.com/50247550/video",
        ]), mock.patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as caught:
                tool.main()
        self.assertEqual(caught.exception.code, 2)

    @mock.patch("bilibili_tool.get_space_videos", return_value=[])
    @mock.patch("bilibili_tool.fetch_single_video")
    def test_main_without_url_still_uses_space_mode(self, mock_fetch, mock_space):
        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch("sys.argv", ["bilibili_tool.py", "--base-dir", tmpdir, "--dry-run"]):
            tool.main()
        mock_fetch.assert_not_called()
        mock_space.assert_called_once()
        self.assertIn("space.bilibili.com", mock_space.call_args.args[0])

    @mock.patch('bilibili_tool.save_summary')
    @mock.patch('bilibili_tool.generate_summary', return_value='summary')
    @mock.patch('bilibili_tool.convert_subtitle_to_md', return_value='/tmp/asr-subtitle.md')
    @mock.patch('bilibili_tool.shared.enhance_subtitle_text', return_value='整理后的字幕')
    @mock.patch('bilibili_tool.shared.correct_asr_text', return_value='校对后的字幕')
    @mock.patch('bilibili_tool.transcribe_video_with_asr', return_value='原始转写')
    @mock.patch('bilibili_tool.get_available_subtitles', return_value=[])
    def test_process_video_uses_asr_fallback_when_no_subtitles(
        self,
        mock_get_subtitles,
        mock_transcribe,
        mock_correct,
        mock_enhance,
        mock_convert,
        mock_generate,
        mock_save,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = tool.load_config()
            config = config.__class__(
                base_dir=Path(tmpdir),
                content_subdir=config.content_subdir,
                default_channel_url=config.default_channel_url,
                default_channel_name=config.default_channel_name,
                default_limit=config.default_limit,
                minimax_base_url=config.minimax_base_url,
                minimax_model=config.minimax_model,
            )
            context = tool.build_space_context("https://space.bilibili.com/513194466/video", config)
            context.subtitles_dir.mkdir(parents=True, exist_ok=True)
            context.summaries_dir.mkdir(parents=True, exist_ok=True)

            success = tool.process_video(
                {'id': 'BVTEST123', 'title': '测试标题', 'upload_date': '20260320'},
                context,
                config,
                cookies_file=None,
                cookies_from_browser='chrome',
            )

        self.assertTrue(success)
        mock_get_subtitles.assert_called_once()
        mock_transcribe.assert_called_once_with(
            'https://www.bilibili.com/video/BVTEST123',
            'BVTEST123',
            None,
            'chrome',
        )
        mock_correct.assert_called_once()
        mock_enhance.assert_called_once_with('测试标题', '校对后的字幕', config)
        mock_convert.assert_called_once()
        self.assertEqual(mock_convert.call_args.args[3], 'asr-zh')
        mock_generate.assert_called_once()
        mock_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
