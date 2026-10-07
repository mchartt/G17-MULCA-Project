"""
Links -- which channels each bot serves -- and the store that keeps them,
with each bot's paused state and where each user last spoke, across
restarts and redeploys.
"""

import pytest

from mulca_discord.links import Link, LinkStore, link_for_channel

GUILD = 900


def link(text, voice=None, *, bot=1, guild=GUILD, transcripts=False) -> Link:
    return Link(
        text_channel_id=text,
        guild_id=guild,
        bot_id=bot,
        voice_channel_id=voice,
        post_voice_transcripts=transcripts,
    )


def test_the_memory_belongs_to_the_text_channel_not_a_name():
    assert link(111, 222).conversation_id == "channel:111"


def test_a_link_owns_its_text_and_voice_channel():
    alpha = link(111, 222)

    assert alpha.owns_channel(111) and alpha.owns_channel(222)
    assert not alpha.owns_channel(333)
    assert not link(111).owns_channel(None)
    assert link_for_channel([alpha, link(333)], 222) is alpha


def test_links_survive_reopening_the_store(tmp_path):
    path = tmp_path / "mulca.db"
    store = LinkStore(path)
    store.save(link(111, 222, transcripts=True), created_by=5)
    store.save(link(333, bot=2))
    store.close()

    reopened = LinkStore(path)

    assert reopened.links_for(1) == [link(111, 222, transcripts=True)]
    assert reopened.links_for(2) == [link(333, bot=2)]
    assert reopened.link_for_channel(222) == link(111, 222, transcripts=True)


def test_saving_a_linked_text_channel_again_updates_it():
    store = LinkStore(":memory:")
    store.save(link(111))

    previous = store.save(link(111, 222))

    assert previous == link(111)
    assert store.all_links() == [link(111, 222)]


def test_unlinking_by_either_channel_removes_the_link():
    store = LinkStore(":memory:")
    store.save(link(111, 222))

    assert store.remove(222) == link(111, 222)
    assert store.all_links() == []
    assert store.remove(111) is None


@pytest.mark.parametrize(
    ("existing", "new", "reason"),
    [
        (link(111), link(111, bot=2), "already served by another MULCA bot"),
        (link(111, 222), link(333, 222), "already linked to <#111>"),
        (link(111, 222), link(333, 444), "one voice channel per server"),
        (link(111, 222), link(222), "is the voice channel of <#111>"),
    ],
    ids=[
        "text channel taken by another bot",
        "voice channel taken",
        "second voice channel in one server",
        "a voice channel as text channel",
    ],
)
def test_conflicting_links_are_refused(existing, new, reason):
    store = LinkStore(":memory:")
    store.save(existing)

    assert any(reason in problem for problem in store.conflicts(new))
    with pytest.raises(ValueError):
        store.save(new)
    assert store.all_links() == [existing]


def test_the_same_bot_may_have_voice_in_two_different_servers():
    store = LinkStore(":memory:")
    store.save(link(111, 222, guild=900))

    store.save(link(333, 444, guild=901))

    assert len(store.links_for(1)) == 2


def test_paused_survives_reopening_the_store(tmp_path):
    path = tmp_path / "mulca.db"
    store = LinkStore(path)
    store.register_bot(1, "MULCA", is_primary=True)
    store.set_paused(1, True)
    store.close()

    reopened = LinkStore(path)

    assert reopened.is_paused(1)
    assert not reopened.is_paused(2)


def test_where_each_user_last_spoke_is_remembered(tmp_path):
    path = tmp_path / "mulca.db"
    store = LinkStore(path)
    store.save(link(111))
    store.save(link(333))
    store.remember_speaker(5, 111)
    store.remember_speaker(5, 333)
    store.close()

    reopened = LinkStore(path)

    assert reopened.last_link_for(5) == link(333)
    assert reopened.last_link_for(6) is None

    # An unlinked channel is no longer anyone's group memory.
    reopened.remove(333)
    assert reopened.last_link_for(5) is None


def test_a_store_from_before_per_link_dms_is_upgraded_with_dms_off(tmp_path):
    import sqlite3

    path = tmp_path / "mulca.db"
    old = sqlite3.connect(path)
    old.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta VALUES ('schema_version', '1');
        CREATE TABLE links (
            text_channel_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL,
            voice_channel_id INTEGER UNIQUE,
            post_voice_transcripts INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER,
            created_at REAL
        );
        INSERT INTO links (text_channel_id, guild_id, bot_id, voice_channel_id)
            VALUES (111, 900, 1, 222);
        """
    )
    old.commit()
    old.close()

    store = LinkStore(path)

    assert store.all_links() == [link(111, 222)]
    assert not store.all_links()[0].allow_dms
    store.save(Link(111, 900, 1, 222, allow_dms=True))
    store.close()
    assert LinkStore(path).all_links()[0].allow_dms


def test_a_bots_models_default_to_the_servers_and_survive_a_restart(tmp_path):
    path = tmp_path / "mulca.db"
    store = LinkStore(path)
    store.register_bot(1, "MULCA", is_primary=True)
    assert store.models_for(1) == ("", "")
    assert store.models_for(None) == ("", "")

    store.set_models(1, "gpt-a")
    store.set_models(1, "gpt-b", "gpt-c")
    store.set_models(1, "gpt-d")
    store.close()

    assert LinkStore(path).models_for(1) == ("gpt-d", "gpt-c")


def test_a_file_from_before_per_bot_models_gains_the_columns(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        """
        CREATE TABLE bots (
            bot_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            is_primary INTEGER NOT NULL DEFAULT 0,
            paused INTEGER NOT NULL DEFAULT 0,
            token TEXT,
            added_by INTEGER,
            added_at REAL
        );
        INSERT INTO bots (bot_id, name, is_primary) VALUES (1, 'MULCA', 1);
        """
    )
    old.commit()
    old.close()

    store = LinkStore(path)

    assert store.models_for(1) == ("", "")
    store.set_models(1, "gpt-a")
    assert store.models_for(1) == ("gpt-a", "")


def test_hour_limits_from_before_dollars_are_dropped_for_the_defaults(tmp_path):
    import sqlite3

    path = tmp_path / "mulca.db"
    old = sqlite3.connect(path)
    old.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta VALUES ('schema_version', '4');
        CREATE TABLE usage (
            bot_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            active_minutes INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (bot_id, day)
        );
        CREATE TABLE limits (
            scope TEXT PRIMARY KEY,
            daily_minutes INTEGER,
            weekly_minutes INTEGER
        );
        INSERT INTO limits VALUES ('each', 240, 600);
        """
    )
    old.commit()
    old.close()

    store = LinkStore(path)

    assert store.limit("each") is None
    store.set_limit("each", 1.0, 2.0, 3.0)
    store.add_cost(1, "2026-10-07", "main", (1, 2, 3, 4, 5, 6), 0.5)
    store.close()

    reopened = LinkStore(path)
    assert reopened.limit("each") == (1.0, 2.0, 3.0)
    assert reopened.cost(1, "2026-10-07", "2026-10-07") == 0.5
