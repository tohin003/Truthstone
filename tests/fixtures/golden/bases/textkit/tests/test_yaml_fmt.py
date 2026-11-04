from textkit.formats.yaml_fmt import render


def test_render_list_of_mappings():
    assert render([["Ada", 36], ["Grace", 45]], ["name", "age"]) == (
        "- name: Ada\n  age: 36\n- name: Grace\n  age: 45\n"
    )


def test_values_with_a_colon_are_quoted():
    assert render([["note: urgent"]], ["value"]) == '- value: "note: urgent"\n'
