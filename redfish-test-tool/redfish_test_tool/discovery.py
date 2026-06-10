"""Vendor-neutral resource discovery by walking @odata.id links from the root."""

from redfish_test_tool.exceptions import RedfishError, ResourceNotFound


def odata_id(obj):
    return (obj or {}).get("@odata.id")


class ServiceMap:
    """Caches resolved resource URIs/payloads discovered from /redfish/v1/."""

    def __init__(self, client, system_id=""):
        self.client = client
        self.system_id = system_id
        self._cache = {}
        self.root = None
        self.system = None       # selected ComputerSystem payload
        self.system_uri = None
        self.chassis_list = []   # list of (uri, payload)
        self.manager = None      # first Manager payload
        self.manager_uri = None

    def fetch(self, uri, refresh=False):
        if refresh or uri not in self._cache:
            self._cache[uri] = self.client.get_json(uri)
        return self._cache[uri]

    def discover(self):
        self.root = self.fetch("/redfish/v1/")
        self._discover_system()
        self._discover_chassis()
        self._discover_manager()
        return self

    # -- collections ----------------------------------------------------------

    def _members(self, collection_link_name):
        link = odata_id(self.root.get(collection_link_name))
        if not link:
            return []
        collection = self.fetch(link)
        return [odata_id(m) for m in collection.get("Members", []) if odata_id(m)]

    def _discover_system(self):
        members = self._members("Systems")
        if not members:
            raise ResourceNotFound("No ComputerSystem members found under Systems")
        uri = members[0]
        if self.system_id:
            matches = [m for m in members if m.rstrip("/").split("/")[-1] == self.system_id]
            if not matches:
                raise ResourceNotFound(
                    f"System id '{self.system_id}' not found; available: "
                    + ", ".join(m.rstrip('/').split('/')[-1] for m in members)
                )
            uri = matches[0]
        self.system_uri = uri
        self.system = self.fetch(uri)

    def _discover_chassis(self):
        for uri in self._members("Chassis"):
            try:
                self.chassis_list.append((uri, self.fetch(uri)))
            except RedfishError:
                continue

    def _discover_manager(self):
        members = self._members("Managers")
        if members:
            self.manager_uri = members[0]
            self.manager = self.fetch(self.manager_uri)

    # -- nested resources -------------------------------------------------------

    def refresh_system(self):
        self.system = self.fetch(self.system_uri, refresh=True)
        return self.system

    def reset_action(self):
        """Return (target_uri, allowable_values) of the system Reset action."""
        actions = (self.system or {}).get("Actions", {})
        reset = actions.get("#ComputerSystem.Reset", {})
        target = reset.get("target")
        if not target:
            raise ResourceNotFound("ComputerSystem Reset action not found")
        allowed = reset.get("ResetType@Redfish.AllowableValues")
        if allowed is None:
            info_uri = odata_id(reset.get("@Redfish.ActionInfo")
                                if isinstance(reset.get("@Redfish.ActionInfo"), dict)
                                else None) or reset.get("@Redfish.ActionInfo")
            if isinstance(info_uri, str):
                try:
                    info = self.fetch(info_uri)
                    for param in info.get("Parameters", []):
                        if param.get("Name") == "ResetType":
                            allowed = param.get("AllowableValues")
                except RedfishError:
                    pass
        return target, allowed

    def chassis_link(self, chassis_payload, name):
        """Resolve an optional chassis sub-resource (Thermal, Power, Sensors, ...)."""
        return odata_id(chassis_payload.get(name))

    def session_service(self):
        uri = odata_id(self.root.get("SessionService"))
        return self.fetch(uri) if uri else None

    def sessions_collection_uri(self):
        links = self.root.get("Links", {}).get("Sessions", {})
        uri = odata_id(links)
        if uri:
            return uri
        svc = self.session_service()
        if svc:
            return odata_id(svc.get("Sessions"))
        return None

    def account_service(self):
        uri = odata_id(self.root.get("AccountService"))
        return self.fetch(uri) if uri else None

    def accounts_collection_uri(self):
        svc = self.account_service()
        if svc:
            return odata_id(svc.get("Accounts"))
        return None

    def log_services(self):
        """Yield (owner, uri, payload) for every LogService on Manager and System."""
        results = []
        for owner, payload in (("Manager", self.manager), ("System", self.system)):
            if not payload:
                continue
            coll_uri = odata_id(payload.get("LogServices"))
            if not coll_uri:
                continue
            try:
                coll = self.fetch(coll_uri)
            except RedfishError:
                continue
            for member in coll.get("Members", []):
                uri = odata_id(member)
                if not uri:
                    continue
                try:
                    results.append((owner, uri, self.fetch(uri)))
                except RedfishError:
                    continue
        return results

    def find_sel(self):
        """Locate the SEL-like log service: prefer id/name containing 'SEL'."""
        services = self.log_services()
        for owner, uri, payload in services:
            ident = (payload.get("Id", "") + payload.get("Name", "")).lower()
            if "sel" in ident:
                return owner, uri, payload
        return services[0] if services else None
