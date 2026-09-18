import json
from pathlib import Path

from kernel.models.api import ApiCall, ApiSlot
from kernel.utils.validators import ApiValidator
from kernel.exceptions import LoadApiTemplatesError, EmptyApiTemplatesError


class ApiFactory:
    """
    Builds ApiSlot objects from JSON API templates.

    Loads, validates, and injects runtime context into API
      configurations, then compiles them into executeable slots.

    Invalid templates are dropped and counted via 'dropped_apis'.

    Output is exposed through 'api_slots' after 'build()' is called.
    """

    def __init__(self, templates_path: Path, context: dict) -> None:
        """
        Args:
            api_templates_path | Path: Path to JSON file
              containing API templates.

            context | dict[str, Any]: Runtime values used for
              template injection (e.g. phone number).
        """
        self._templates_path = templates_path
        self._context = context

        self._dropped_apis = 0
        self._api_slots: list[ApiSlot] = []

    @property
    def templates_path(self) -> Path:
        return self._templates_path

    @property
    def context(self) -> dict:
        return self._context.copy()

    @property
    def dropped_apis(self) -> int:
        return self._dropped_apis

    @property
    def api_slots(self) -> tuple[ApiSlot, ...]:
        """
        Returns the builted tuple of executable API slots.

        These slots are fully validated and contain injected
          runtime context, ready for scheduling or execution.

        Returns:
            tuple[ApiSlot, ...]: Final runtime API slot objects.
        """
        return tuple(self._api_slots)

    @property
    def count(self) -> int:
        return len(self._api_slots)

    def _load(self) -> list[dict]:
        """
        Loads raw API templates from the JSON file.

        Returns:
            list[dict[str, Any]]: Parsed JSON configuration list.

        Raises:
            LoadApiTemplatesError: If file is missing or
              JSON is malformed.
        """
        try:
            with open(self._templates_path, "r", encoding="utf-8") as f:
                return json.load(f)

        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise LoadApiTemplatesError(self._templates_path) from e

    def _validate(self, templates: list[dict]) -> list[dict]:
        """
        Filters and validates API templates.

        Invalid templates are dropped and counted internally.

        Args:
            templates | list[dict]: Raw loaded API
              configurations.

        Raises:
            EmptyApiTemplatesError: If no valid templates remain
              after validation.
        """
        valids = []

        for api_config in templates:

            if ApiValidator.validate(api_config):
                valids.append(api_config)
            else:
                self._dropped_apis += 1

        if not valids:
            raise EmptyApiTemplatesError(self._templates_path)

        return valids

    def _create_slot(self, index: int, api: dict) -> ApiSlot:
        """
        Converts a validated and injected API configuration
          into an ApiSlot runtime object.

        Args:
            api_config | dict: Fully validated and
              context-injected API config.

        Returns:
            ApiSlot: Runtime execution-ready API slot.
        """
        return ApiSlot(
            index=index,
            call=ApiCall(
                source=api["source"],
                url=api["url"],
                method=api["method"],
                json=api.get("json"),
                data=api.get("data"),
            ),
            capacity=api["capacity"],
            ticket=api["ticket"],
        )

    def _inject_context(self, obj, context: dict):
        """
        Recursively injects runtime context values into
          template structures.

        Supports:
            - dict (recursive traversal)
            - list (recursive traversal)
            - str (format injection using '.format(**context)')
            - other types passed

        Args:
            obj: Template structure (dict, list, or string).

            context | Dict: Runtime values used for injection.

        Returns:
            Fully resolved structure with injected values.
        """
        if isinstance(obj, dict):
            return {k: self._inject_context(v, context) for k, v in obj.items()}

        if isinstance(obj, list):
            return [self._inject_context(v, context) for v in obj]

        if isinstance(obj, str):
            try:
                return obj.format(**context)

            except KeyError:
                return obj

        return obj

    def build(self) -> None:
        """
        Compiles API templates into executable runtime ApiSlots.

        This method executes the full factory pipeline:
            1. Loads raw API templates from the JSON file
            2. Validates each template using ApiValidator
            3. Injects runtime context values into templates
            4. Constructs ApiSlot objects from validated data

        Side effects:
            - Populates 'self._api_slots' with compiled ApiSlot objects
            - Resets and updates 'self._dropped_apis' counter
        """
        self._api_slots.clear()
        self._dropped_apis = 0

        loaded_templates = self._load()
        validated_templates = self._validate(loaded_templates)

        for idx, api in enumerate(validated_templates, start=1):
            self._api_slots.append(
                self._create_slot(
                    index=idx,
                    api=self._inject_context(api, self._context),
                )
            )
