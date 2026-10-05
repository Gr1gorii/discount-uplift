from streamlit.testing.v1 import AppTest

from src.data import ROOT


def test_app_runs_and_discount_reduces_profit():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    assert not app.exception
    initial_profit = app.metric[1].value
    app.sidebar.selectbox[0].set_value("Italiano").run()
    assert not app.exception
    assert app.title[0].value == "A chi inviare un'offerta?"
    assert app.metric[1].value == initial_profit
    app.sidebar.slider[1].set_value(5).run()
    assert not app.exception
    assert app.metric[1].value != initial_profit
    assert len(app.dataframe) >= 3
    app.sidebar.select_slider[0].set_value(0).run()
    assert not app.exception
    assert app.metric[1].value == "+$0"
    app.sidebar.select_slider[0].set_value(100).run()
    assert app.metric[2].value == "+$0"
    app.sidebar.slider[0].set_value(0.5).run()
    assert not app.exception
